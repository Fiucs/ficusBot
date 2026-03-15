#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
网关主程序模块

功能说明:
    - 管理所有平台监听器的生命周期
    - 协调拦截器链和消息总线
    - 从项目配置加载渠道配置
    - 提供统一的启动/停止接口
    - 支持 HTTP API 服务挂载

核心方法:
    - use: 添加拦截器（链式调用）
    - mount_http: 挂载 FastAPI 服务
    - load_from_config: 从配置加载监听器
    - start/stop: 启动/停止网关
"""

import asyncio
import signal
from typing import Dict, Any, List, Optional, Type
from loguru import logger

from .bot.message_bus import MessageBus
from .bot.base_listener import BaseListener
from .bot.core_processor import CoreProcessor, EchoProcessor
from .bot.listeners import get_listener_class
from .interceptor.base import Interceptor, InterceptResult
from .interceptor.interceptor_chain import InterceptorChain
from .interceptor.builtins import AuthInterceptor, RateLimitInterceptor, SensitiveWordInterceptor


class Gateway:
    """
    统一网关
    
    协调拦截器链和消息总线，管理所有平台监听器。
    支持 HTTP API 服务挂载，实现 Bot 和 HTTP 的统一入口。
    
    配置项:
        - agent: Agent 实例
        - use_echo_processor: 是否使用回声处理器（测试模式）
        - agent_registry: Agent 注册中心
        - enable_default_interceptors: 是否启用默认拦截器（默认 True）
    
    核心方法:
        - use(interceptor, direction): 添加拦截器
        - mount_http(app): 挂载 HTTP 服务
        - load_from_config(): 从配置加载监听器
        - start()/stop(): 启动/停止网关
    """
    
    def __init__(
        self, 
        agent=None, 
        use_echo_processor: bool = False, 
        agent_registry=None,
        enable_default_interceptors: bool = True
    ):
        self.incoming_chain = InterceptorChain()
        self.outgoing_chain = InterceptorChain()
        self.bus = MessageBus()
        self.listeners: Dict[str, BaseListener] = {}
        self._agent = agent
        self._agent_registry = agent_registry
        self._use_echo_processor = use_echo_processor
        self._processor = None
        self._running = False
        self._dispatch_task = None
        self._http_app = None
        
        # 注册默认拦截器
        if enable_default_interceptors:
            self._register_default_interceptors()
    
    def _register_default_interceptors(self) -> None:
        """
        注册默认拦截器。
        
        从配置文件读取拦截器参数，注册到 incoming_chain。
        """
        from ..config.configloader import GLOBAL_CONFIG
        
        interceptor_config = GLOBAL_CONFIG.get("interceptor", {})
        
        # 权限验证拦截器
        auth_config = interceptor_config.get("auth", {})
        if auth_config.get("enabled", True):
            self.incoming_chain.add(AuthInterceptor(
                whitelist=auth_config.get("whitelist", []),
                blacklist=auth_config.get("blacklist", [])
            ))
            logger.info("[Gateway] 已注册 AuthInterceptor")
        
        # 限流拦截器
        rate_limit_config = interceptor_config.get("rate_limit", {})
        if rate_limit_config.get("enabled", True):
            self.incoming_chain.add(RateLimitInterceptor(
                max_requests=rate_limit_config.get("max_requests", 10),
                window=rate_limit_config.get("window", 60)
            ))
            logger.info("[Gateway] 已注册 RateLimitInterceptor")
        
        # 敏感词过滤拦截器
        sensitive_config = interceptor_config.get("sensitive_word", {})
        if sensitive_config.get("enabled", True):
            self.incoming_chain.add(SensitiveWordInterceptor(
                words=sensitive_config.get("words", []),
                replace_char=sensitive_config.get("replace_char", "***")
            ))
            logger.info("[Gateway] 已注册 SensitiveWordInterceptor")
    
    def use(self, interceptor: Interceptor, direction: str = "incoming") -> "Gateway":
        """添加拦截器（链式调用）"""
        if direction == "incoming":
            self.incoming_chain.add(interceptor)
        elif direction == "outgoing":
            self.outgoing_chain.add(interceptor)
        else:
            logger.warning(f"[Gateway] 未知的拦截方向: {direction}")
        return self
    
    def use_all(self, interceptors: List[Interceptor], direction: str = "incoming") -> "Gateway":
        """批量添加拦截器"""
        for interceptor in interceptors:
            self.use(interceptor, direction)
        return self
    
    async def process_incoming(self, data: dict, source: str) -> bool:
        """处理进入消息（供 Listener 调用）"""
        result = await self.incoming_chain.execute(data)
        
        if not result.passed:
            await self._send_intercept_response(data, result, source)
            return False
        
        await self.bus.publish("incoming", result.data, source)
        return True
    
    async def process_outgoing(self, data: dict, source: str) -> bool:
        """处理响应消息（供 CoreProcessor 调用）"""
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
        """发送拦截响应"""
        if not result.response:
            return
        
        outgoing = {
            "listener": original_data.get("listener", ""),
            "chat_id": original_data.get("chat_id", ""),
            "content": result.response,
            "thread_id": original_data.get("thread_id"),
        }
        
        await self.bus.publish("outgoing", outgoing, source="interceptor")
    
    def mount_http(self, app=None) -> "Gateway":
        """挂载 FastAPI 服务"""
        from .http.app import create_app
        
        if app is None:
            app = create_app(self)
        
        self._http_app = app
        logger.info("[Gateway] FastAPI 服务已挂载")
        return self
    
    def load_from_config(self) -> int:
        """从项目配置加载监听器"""
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
        """提取监听器配置"""
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
            config["appid"] = channel_config.get("appid", "")
            config["secret"] = channel_config.get("secret", "")
            config["image_save_dir"] = channel_config.get("image_save_dir", "")
        
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
        """添加监听器"""
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
        """移除监听器"""
        if name not in self.listeners:
            return False
        
        del self.listeners[name]
        logger.info(f"[Gateway] 移除监听器: {name}")
        return True
    
    def get_listener(self, name: str) -> Optional[BaseListener]:
        """获取监听器"""
        return self.listeners.get(name)
    
    def set_agent(self, agent) -> None:
        """设置 Agent 实例"""
        self._agent = agent
        if self._processor:
            self._processor.set_agent(agent)
    
    async def start(self) -> bool:
        """启动网关"""
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
        """停止网关"""
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
        """持续运行网关"""
        if not self._running:
            await self.start()
        
        from agent.utils.shutdown import shutdown, register_shutdown_callback
        
        stop_event = asyncio.Event()
        loop = asyncio.get_event_loop()
        
        def signal_handler():
            logger.info("[Gateway] 收到停止信号")
            shutdown("用户按下 Ctrl+C")
            stop_event.set()
        
        def on_shutdown():
            loop.call_soon_threadsafe(stop_event.set)
        
        register_shutdown_callback(on_shutdown)
        
        signal_handlers = []
        
        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, signal_handler)
                signal_handlers.append(sig)
        except NotImplementedError:
            import sys
            if sys.platform == 'win32':
                def win_signal_handler(signum, frame):
                    logger.info("[Gateway] 收到停止信号 (Windows)")
                    shutdown("用户按下 Ctrl+C")
                    loop.call_soon_threadsafe(stop_event.set)
                
                signal.signal(signal.SIGINT, win_signal_handler)
                signal.signal(signal.SIGTERM, win_signal_handler)
        
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
