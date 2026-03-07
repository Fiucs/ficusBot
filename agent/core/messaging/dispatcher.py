#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :dispatcher.py
# @Time      :2026/03/07
# @Author    :Ficus

"""
消息分发器模块

该模块实现消息分发器，根据消息类型路由到不同的处理器。
"""
from typing import Callable, Awaitable, Dict, Optional, TYPE_CHECKING
from loguru import logger

from agent.core.messaging.message import Message, MessageResponse, MessageType
from agent.core.messaging.channel import MessageChannel

if TYPE_CHECKING:
    pass


class MessageDispatcher:
    """
    消息分发器
    
    功能说明:
        - 根据消息类型路由到不同的处理器
        - 支持自定义处理器注册
        - 支持默认处理器
    
    核心方法:
        - register: 注册处理器
        - unregister: 注销处理器
        - dispatch: 分发消息
    """
    
    def __init__(self, channel: Optional[MessageChannel] = None):
        """
        初始化消息分发器
        
        Args:
            channel: 消息通道实例
        """
        self._channel = channel or MessageChannel()
        self._handlers: Dict[MessageType, Callable[[Message], Awaitable[MessageResponse]]] = {}
        self._default_handler: Optional[Callable[[Message], Awaitable[MessageResponse]]] = None
    
    @property
    def channel(self) -> MessageChannel:
        """获取消息通道"""
        return self._channel
    
    def register(
        self,
        message_type: MessageType,
        handler: Callable[[Message], Awaitable[MessageResponse]]
    ) -> None:
        """
        注册处理器
        
        Args:
            message_type: 消息类型
            handler: 处理函数
        """
        self._handlers[message_type] = handler
        logger.debug(f"[MessageDispatcher] 注册处理器: {message_type.value}")
    
    def unregister(self, message_type: MessageType) -> bool:
        """
        注销处理器
        
        Args:
            message_type: 消息类型
            
        Returns:
            是否成功注销
        """
        if message_type in self._handlers:
            del self._handlers[message_type]
            return True
        return False
    
    def set_default_handler(
        self,
        handler: Callable[[Message], Awaitable[MessageResponse]]
    ) -> None:
        """
        设置默认处理器
        
        Args:
            handler: 默认处理函数
        """
        self._default_handler = handler
        logger.debug("[MessageDispatcher] 设置默认处理器")
    
    async def dispatch(
        self,
        message: Message,
        timeout: float = 60.0
    ) -> MessageResponse:
        """
        分发消息到对应处理器
        
        Args:
            message: 消息对象
            timeout: 超时时间
            
        Returns:
            响应对象
        """
        handler = self._handlers.get(message.type)
        
        if handler is None:
            if self._default_handler:
                handler = self._default_handler
            else:
                return MessageResponse(
                    message_id=message.id,
                    success=False,
                    error=f"No handler for message type: {message.type.value}"
                )
        
        try:
            return await handler(message)
        except Exception as e:
            logger.error(f"[MessageDispatcher] 处理异常: {e}")
            return MessageResponse(
                message_id=message.id,
                success=False,
                error=str(e)
            )
    
    async def publish(
        self,
        message: Message,
        timeout: float = 60.0
    ) -> MessageResponse:
        """
        发布消息（通过分发器处理）
        
        Args:
            message: 消息对象
            timeout: 超时时间
            
        Returns:
            响应对象
        """
        return await self.dispatch(message, timeout)
