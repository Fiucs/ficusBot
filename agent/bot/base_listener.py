#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :base_listener.py
# @Time      :2026/02/22
# @Author    :Ficus

"""
基础监听器模块

功能说明:
    - 定义所有监听器必须实现的抽象接口
    - 提供通用的消息处理逻辑
    - 管理监听器的生命周期

核心方法:
    - start: 启动监听器（建立连接、开始接收消息）
    - stop: 停止监听器（关闭连接、清理资源）
    - send_message: 向指定目标发送消息
    - _convert_to_unified: 平台原始消息转换为统一格式

使用方式:
    继承 BaseListener 类，实现所有抽象方法。
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from loguru import logger

from .message_bus import MessageBus, UnifiedMessage, OutgoingMessage


class BaseListener(ABC):
    """
    基础监听器抽象类
    
    所有平台监听器必须继承此类并实现所有抽象方法。
    
    功能说明:
        - 定义监听器的标准接口
        - 提供消息发布/订阅的通用逻辑
        - 管理监听器的生命周期
    
    核心属性:
        - name: 监听器唯一标识
        - config: 平台配置（token、api_base等）
        - bus: 消息总线引用
    
    核心方法:
        - start: 启动监听器
        - stop: 停止监听器
        - send_message: 发送消息
        - _convert_to_unified: 转换消息格式
    
    使用示例:
        class TelegramListener(BaseListener):
            async def start(self):
                # 初始化并连接
                pass
            
            async def stop(self):
                # 断开连接
                pass
            
            async def send_message(self, target, content, **kwargs):
                # 发送消息
                pass
            
            async def _convert_to_unified(self, raw):
                # 转换消息格式
                pass
    """
    
    def __init__(self, name: str, config: Dict[str, Any], bus: MessageBus):
        """
        初始化监听器。
        
        参数:
            name: 监听器唯一标识，如 "telegram"
            config: 平台配置字典
            bus: 消息总线实例
        """
        self.name = name
        self.config = config
        self.bus = bus
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._bot_info: Optional[Dict[str, Any]] = None
    
    @property
    def is_running(self) -> bool:
        """检查监听器是否运行中"""
        return self._running
    
    @property
    def bot_info(self) -> Optional[Dict[str, Any]]:
        """获取机器人信息"""
        return self._bot_info
    
    @abstractmethod
    async def start(self) -> bool:
        """
        启动监听器。
        
        实现要求:
            1. 初始化平台 SDK
            2. 建立连接
            3. 订阅消息总线 outgoing 事件
            4. 开始接收消息
        
        返回:
            bool: 启动是否成功
        """
        pass
    
    @abstractmethod
    async def stop(self) -> bool:
        """
        停止监听器。
        
        实现要求:
            1. 停止接收消息
            2. 关闭平台连接
            3. 清理资源
            4. 取消所有后台任务
        
        返回:
            bool: 停止是否成功
        """
        pass
    
    @abstractmethod
    async def send_message(self, target: Dict[str, str], content: str, **kwargs) -> Dict[str, Any]:
        """
        向指定目标发送消息。
        
        参数:
            target: 目标信息字典，包含:
                - chat_id: 会话ID
                - thread_id: 线程ID（可选）
            content: 消息内容
            **kwargs: 其他参数（如 reply_to）
        
        返回:
            Dict: 发送结果，包含:
                - success: 是否成功
                - message_id: 消息ID（可选）
                - error: 错误信息（可选）
        """
        pass
    
    @abstractmethod
    async def _convert_to_unified(self, raw: Any) -> UnifiedMessage:
        """
        将平台原始消息转换为统一格式。
        
        参数:
            raw: 平台原始消息对象
        
        返回:
            UnifiedMessage: 统一格式消息
        """
        pass
    
    async def _publish_incoming(self, raw_data: Any) -> None:
        """
        将原始消息转换为统一格式并发布到总线。
        
        参数:
            raw_data: 平台原始消息
        """
        try:
            logger.info(f"[{self.name}] 正在转换消息格式...")
            unified = await self._convert_to_unified(raw_data)
            unified.listener = self.name
            
            logger.info(f"[{self.name}] 消息转换完成: chat_id={unified.chat_id}, user_id={unified.user_id}, type={unified.type}")
            logger.info(f"[{self.name}] 消息内容: {unified.content[:100]}...")
            
            await self.bus.publish(
                "incoming",
                unified.to_dict(),
                source=self.name
            )
            
            logger.info(
                f"[{self.name}] ✅ 消息已发布到总线: chat_id={unified.chat_id}, "
                f"user_id={unified.user_id}, type={unified.type}"
            )
        except Exception as e:
            logger.error(f"[{self.name}] ❌ 消息转换失败: {e}")
            import traceback
            logger.error(f"[{self.name}] 错误堆栈:\n{traceback.format_exc()}")
    
    async def _handle_outgoing(self, data: dict) -> None:
        """
        处理 outgoing 事件。
        
        参数:
            data: 发送消息数据
        """
        if data.get("listener") != self.name:
            return
        
        try:
            target = {
                "chat_id": data["chat_id"],
                "thread_id": data.get("thread_id")
            }
            
            result = await self.send_message(
                target=target,
                content=data.get("content", ""),
                reply_to=data.get("reply_to")
            )
            
            if result.get("success"):
                logger.debug(f"[{self.name}] 消息发送成功: chat_id={target['chat_id']}")
            else:
                logger.error(f"[{self.name}] 消息发送失败: {result.get('error')}")
                
        except Exception as e:
            logger.error(f"[{self.name}] 处理 outgoing 事件失败: {e}")
    
    def _create_task(self, coro, name: str = None) -> asyncio.Task:
        """
        创建并跟踪后台任务。
        
        参数:
            coro: 协程对象
            name: 任务名称（可选）
        
        返回:
            asyncio.Task: 任务对象
        """
        task = asyncio.create_task(coro)
        if name:
            task.set_name(name)
        self._tasks.append(task)
        return task
    
    async def _cancel_all_tasks(self) -> None:
        """取消所有后台任务"""
        for task in self._tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._tasks.clear()
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name} running={self._running}>"
