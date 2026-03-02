#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :gateway.py
# @Time      :2026/02/22
# @Author    :Ficus

"""
网关主程序模块

功能说明:
    - 管理所有平台监听器的生命周期
    - 协调拦截器链和消息总线
    - 从项目配置加载渠道配置
    - 提供统一的启动/停止接口

核心方法:
    - start: 启动网关
    - stop: 停止网关
    - add_listener: 添加监听器
    - get_listener: 获取监听器
    - use: 添加拦截器
    - process_incoming: 处理进入消息
    - process_outgoing: 处理响应消息
    - mount_http: 挂载 FastAPI 服务

配置来源:
    从 config.json 的 bot.channels 中读取各平台配置
"""

import asyncio
import signal
from typing import Dict, Any, List, Optional, Type
from loguru import logger

from .message_bus import MessageBus
from .base_listener import BaseListener
from .core_processor import CoreProcessor, EchoProcessor
from .listeners import get_listener_class
from .interceptor.base import Interceptor, InterceptResult
from .interceptor.chain import InterceptorChain


class Gateway:
    """
    统一网关
    
    协调拦截器链和消息总线，管理所有平台监听器。
    
    功能说明:
        - 管理监听器生命周期
        - 协调拦截器链执行
        - 协调消息总线传递
        - 处理拦截响应
    
    核心方法:
        - start: 启动网关
        - stop: 停止网关
        - add_listener: 添加监听器
        - remove_listener: 移除监听器
        - get_listener: 获取监听器
        - use: 添加拦截器
        - process_incoming: 处理进入消息
        - process_outgoing: 处理响应消息
        - mount_http: 挂载 FastAPI 服务
    
    流程:
        1. 消息进入 → 执行 incoming_chain → 发布到 MessageBus
        2. 消息处理 → CoreProcessor → 发布到 MessageBus
        3. 响应发送 → 执行 outgoing_chain → 发送到平台
    
    使用示例:
        gateway = Gateway(agent=agent)
        
        # 链式添加拦截器
        gateway.use(AuthInterceptor()) \\
               .use(RateLimitInterceptor()) \\
               .use(SensitiveWordInterceptor())
        
        # 加载监听器
        gateway.load_from_config()
        
        # 启动
        await gateway.start()
    """
    
    def __init__(self, agent=None, use_echo_processor: bool = False, agent_registry=None):
        """
        初始化网关。
        
        Args:
            agent: Agent 实例（用于核心处理器）
            use_echo_processor: 是否使用回声处理器（测试用）
            agent_registry: Agent 注册中心（支持多 Agent 和命令处理）
        """
        # 拦截器链（独立于 MessageBus）
        self.incoming_chain = InterceptorChain()
        self.outgoing_chain = InterceptorChain()
        
        # 消息总线（纯消息传递）
        self.bus = MessageBus()
        
        # 监听器管理
        self.listeners: Dict[str, BaseListener] = {}
        
        # Agent 和处理器
        self._agent = agent
        self._agent_registry = agent_registry
        self._use_echo_processor = use_echo_processor
        self._processor = None
        
        # 运行状态
        self._running = False
        self._dispatch_task = None
        self._http_app = None
    
    def use(
        self, 
        interceptor: Interceptor, 
        direction: str = "incoming"
    ) -> "Gateway":
        """
        添加拦截器（链式调用）。
        
        参数:
            interceptor: 拦截器实例
            direction: 拦截方向（incoming / outgoing）
        
        返回:
            Gateway: self
        """
        if direction == "incoming":
            self.incoming_chain.add(interceptor)
        elif direction == "outgoing":
            self.outgoing_chain.add(interceptor)
        else:
            logger.warning(f"[Gateway] 未知的拦截方向: {direction}")
        return self
    
    def use_all(
        self, 
        interceptors: List[Interceptor], 
        direction: str = "incoming"
    ) -> "Gateway":
        """
        批量添加拦截器。
        
        参数:
            interceptors: 拦截器列表
            direction: 拦截方向
        
        返回:
            Gateway: self
        """
        for interceptor in interceptors:
            self.use(interceptor, direction)
        return self
    
    async def process_incoming(self, data: dict, source: str) -> bool:
        """
        处理进入消息（供 Listener 调用）。
        
        流程:
            1. 执行拦截器链
            2. 如果拦截，发送响应并返回 False
            3. 如果通过，发布到 MessageBus
        
        参数:
            data: 消息数据
            source: 消息来源
        
        返回:
            bool: 是否成功（被拦截返回 False）
        """
        # 执行拦截器链
        result = await self.incoming_chain.execute(data)
        
        if not result.passed:
            # 拦截，发送响应
            await self._send_intercept_response(data, result, source)
            return False
        
        # 通过，发布到 MessageBus
        await self.bus.publish("incoming", result.data, source)
        return True
    
    async def process_outgoing(self, data: dict, source: str) -> bool:
        """
        处理响应消息（供 CoreProcessor 调用）。
        
        流程:
            1. 执行拦截器链
            2. 如果拦截，返回 False
            3. 如果通过，发布到 MessageBus
        
        参数:
            data: 响应数据
            source: 消息来源
        
        返回:
            bool: 是否成功（被拦截返回 False）
        """
        result = await self.outgoing_chain.execute(data)
        
        if not result.passed:
            return False
        
        await self.bus.publish("outgoing", result.data, source)
        return True
    
    async def _send_intercept_response(
        self, 
        original_data: dict, 
        result: InterceptResult, 
        source: str
    ) -> None:
        """
        发送拦截响应。
        
        参数:
            original_data: 原始消息数据
            result: 拦截结果
            source: 消息来源
        """
        if not result.response:
            return
        
        # Bot 消息：发送 outgoing 事件
        outgoing = {
            "listener": original_data.get("listener", ""),
            "chat_id": original_data.get("chat_id", ""),
            "content": result.response,
            "thread_id": original_data.get("thread_id"),
        }
        
        await self.bus.publish("outgoing", outgoing, source="interceptor")
    
    def mount_http(self, app=None) -> "Gateway":
        """
        挂载 FastAPI 服务。
        
        参数:
            app: FastAPI 应用实例（可选）
        
        返回:
            Gateway: self
        """
        from .http.app import create_app
        
        if app is None:
            app = create_app(self)
        
        self._http_app = app
        logger.info("[Gateway] FastAPI 服务已挂载")
        return self
    
    def load_from_config(self) -> int:
        """
        从项目配置加载监听器。
        
        从 config.json 的 bot.channels 中读取配置，
        自动创建并添加启用的监听器。
        
        返回:
            int: 成功加载的监听器数量
        """
        from ..config.configloader import GLOBAL_CONFIG
        
        channels = GLOBAL_CONFIG.get("bot.channels", {})
        loaded_count = 0
        
        for platform, channel_config in channels.items():
            if not channel_config.get("enabled", False):
                logger.debug(f"[Gateway] 跳过未启用的平台: {platform}")
                continue
            
            listener_class = get_listener_class(platform)
            if not listener_class:
                logger.warning(f"[Gateway] 不支持的平台: {platform}")
                continue
            
            name = channel_config.get("name", platform)
            
            config = self._extract_listener_config(platform, channel_config)
            
            if self.add_listener(name, listener_class, config):
                loaded_count += 1
        
        logger.info(f"[Gateway] 从配置加载了 {loaded_count} 个监听器")
        return loaded_count
    
    def _extract_listener_config(self, platform: str, channel_config: dict) -> dict:
        """
        提取监听器配置。
        
        根据平台类型提取对应的配置项。
        
        参数:
            platform: 平台名称
            channel_config: 渠道配置
        
        返回:
            dict: 监听器配置
        """
        config = {}
        
        if platform == "telegram":
            config["token"] = channel_config.get("token", "")
            config["proxy"] = channel_config.get("proxy", "")
        
        elif platform in ["feishu", "lark"]:
            config["app_id"] = channel_config.get("appId", channel_config.get("app_id", ""))
            config["app_secret"] = channel_config.get("appSecret", channel_config.get("app_secret", ""))
            config["webhook_path"] = channel_config.get("webhook_path", "/webhook/lark")
            config["port"] = channel_config.get("port", 8080)
        
        elif platform == "discord":
            config["token"] = channel_config.get("token", "")
        
        elif platform == "qq":
            config["ws_url"] = channel_config.get("ws_url", "")
            config["access_token"] = channel_config.get("access_token", "")
        
        elif platform == "wecom":
            config["corp_id"] = channel_config.get("corp_id", "")
            config["agent_id"] = channel_config.get("agent_id", "")
            config["secret"] = channel_config.get("secret", "")
        
        elif platform == "dingtalk":
            config["app_key"] = channel_config.get("app_key", "")
            config["app_secret"] = channel_config.get("app_secret", "")
        
        elif platform == "slack":
            config["bot_token"] = channel_config.get("bot_token", "")
            config["app_token"] = channel_config.get("app_token", "")
        
        return config
    
    def add_listener(
        self, 
        name: str, 
        listener_class: Type[BaseListener], 
        config: dict
    ) -> bool:
        """
        添加监听器。
        
        参数:
            name: 监听器名称
            listener_class: 监听器类
            config: 监听器配置
        
        返回:
            bool: 是否添加成功
        """
        if name in self.listeners:
            logger.warning(f"[Gateway] 监听器已存在: {name}")
            return False
        
        try:
            listener = listener_class(name, config, self.bus)
            self.listeners[name] = listener
            logger.info(f"[Gateway] 添加监听器: {name} ({listener_class.__name__})")
            return True
        except Exception as e:
            logger.error(f"[Gateway] 添加监听器失败: {name}, 错误: {e}")
            return False
    
    def remove_listener(self, name: str) -> bool:
        """
        移除监听器。
        
        参数:
            name: 监听器名称
        
        返回:
            bool: 是否移除成功
        """
        if name not in self.listeners:
            return False
        
        del self.listeners[name]
        logger.info(f"[Gateway] 移除监听器: {name}")
        return True
    
    def get_listener(self, name: str) -> Optional[BaseListener]:
        """
        获取监听器。
        
        参数:
            name: 监听器名称
        
        返回:
            Optional[BaseListener]: 监听器实例
        """
        return self.listeners.get(name)
    
    def set_agent(self, agent) -> None:
        """
        设置 Agent 实例。
        
        参数:
            agent: Agent 实例
        """
        self._agent = agent
        if self._processor:
            self._processor.set_agent(agent)
    
    async def start(self) -> bool:
        """
        启动网关。
        
        实现逻辑:
            1. 启动消息总线分发循环
            2. 初始化核心处理器
            3. 启动所有监听器
        
        返回:
            bool: 启动是否成功
        """
        if self._running:
            logger.warning("[Gateway] 网关已在运行中")
            return False
        
        try:
            logger.info("[Gateway] 正在启动网关...")
            
            self._dispatch_task = asyncio.create_task(self.bus.dispatch_loop())
            
            if self._use_echo_processor:
                self._processor = EchoProcessor(self.bus)
                self.bus.subscribe("incoming", self._processor.process)
                logger.info("[Gateway] 使用回声处理器（测试模式）")
            else:
                self._processor = CoreProcessor(self.bus, self._agent, self._agent_registry)
                self.bus.subscribe("incoming", self._processor.process)
                logger.info("[Gateway] 使用核心处理器（已启用命令处理和会话持久化）")
            
            success_count = 0
            for name, listener in self.listeners.items():
                try:
                    if await listener.start():
                        success_count += 1
                    else:
                        logger.error(f"[Gateway] 监听器启动失败: {name}")
                except Exception as e:
                    logger.error(f"[Gateway] 监听器启动异常: {name}, 错误: {e}")
            
            self._running = True
            
            logger.info(
                f"[Gateway] 网关已启动, "
                f"监听器: {success_count}/{len(self.listeners)}, "
                f"拦截器: incoming={self.incoming_chain.count}, outgoing={self.outgoing_chain.count}"
            )
            return success_count > 0 or self._http_app is not None
            
        except Exception as e:
            logger.error(f"[Gateway] 网关启动失败: {e}")
            await self.stop()
            return False
    
    async def stop(self) -> None:
        """
        停止网关。
        
        实现逻辑:
            1. 停止所有监听器
            2. 停止消息总线
            3. 清理资源
        """
        if not self._running:
            return
        
        logger.info("[Gateway] 正在停止网关...")
        
        self._running = False
        
        for name, listener in self.listeners.items():
            try:
                await listener.stop()
            except Exception as e:
                logger.error(f"[Gateway] 停止监听器异常: {name}, 错误: {e}")
        
        self.bus.stop()
        
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
        
        logger.info("[Gateway] 网关已停止")
    
    async def run_forever(self) -> None:
        """
        持续运行网关。
        
        阻塞直到收到停止信号。
        """
        if not self._running:
            await self.start()
        
        stop_event = asyncio.Event()
        
        def signal_handler():
            logger.info("[Gateway] 收到停止信号")
            stop_event.set()
        
        try:
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            pass
        
        try:
            await stop_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()
    
    @property
    def is_running(self) -> bool:
        """检查网关是否运行中"""
        return self._running
    
    @property
    def stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "running": self._running,
            "listeners": len(self.listeners),
            "bus_stats": self.bus.stats,
            "processor_stats": self._processor.stats if self._processor else {},
            "interceptors": {
                "incoming": self.incoming_chain.count,
                "outgoing": self.outgoing_chain.count,
            }
        }
    
    def __repr__(self) -> str:
        status = "running" if self._running else "stopped"
        listeners = ", ".join(self.listeners.keys()) if self.listeners else "none"
        return f"<Gateway status={status} listeners=[{listeners}]>"
