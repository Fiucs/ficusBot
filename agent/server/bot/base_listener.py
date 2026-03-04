#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
基础监听器模块

功能说明:
    - 定义所有监听器必须实现的抽象接口
    - 提供通用的消息处理逻辑
    - 管理监听器的生命周期
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from loguru import logger

from .message_bus import MessageBus, UnifiedMessage


class BaseListener(ABC):
    """
    基础监听器抽象类
    
    所有平台监听器必须继承此类并实现所有抽象方法。
    """
    
    PLATFORM_NAME: str = "unknown"
    PLATFORM_DISPLAY_NAME: str = "Unknown"
    
    def __init__(self, name: str, config: Dict[str, Any], bus: MessageBus):
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
        
        Returns:
            bool: 启动是否成功
        """
        pass
    
    @abstractmethod
    async def stop(self) -> bool:
        """
        停止监听器。
        
        Returns:
            bool: 停止是否成功
        """
        pass
    
    @abstractmethod
    async def send_message(self, target: Dict[str, str], content: str, **kwargs) -> Dict[str, Any]:
        """
        向指定目标发送消息。
        
        Args:
            target: 目标信息字典，包含 chat_id, thread_id（可选）
            content: 消息内容
            **kwargs: 其他参数（如 reply_to）
        
        Returns:
            Dict: 发送结果
        """
        pass
    
    @abstractmethod
    async def _convert_to_unified(self, raw: Any) -> UnifiedMessage:
        """
        将平台原始消息转换为统一格式。
        
        Args:
            raw: 平台原始消息对象
        
        Returns:
            UnifiedMessage: 统一格式消息
        """
        pass
    
    async def _publish_incoming(self, raw_data: Any) -> None:
        """将原始消息转换为统一格式并发布到总线"""
        try:
            unified = await self._convert_to_unified(raw_data)
            unified.listener = self.name
            
            await self.bus.publish(
                "incoming",
                unified.to_dict(),
                source=self.name
            )
            
            logger.debug(
                f"[{self.name}] 消息已发布: chat_id={unified.chat_id}, "
                f"user_id={unified.user_id}, type={unified.type}"
            )
        except Exception as e:
            logger.error(f"[{self.name}] 消息转换失败: {e}")
    
    async def _handle_outgoing(self, data: dict) -> None:
        """处理 outgoing 事件"""
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
        """创建并跟踪后台任务"""
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
