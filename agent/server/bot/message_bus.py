#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
消息总线模块

功能说明:
    - 基于 asyncio.Queue 实现的事件总线
    - 支持发布/订阅模式
    - 用于监听器与核心处理器之间的消息传递
"""

import asyncio
import time
from typing import Callable, Awaitable, Dict, List, Any, Optional
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class UnifiedMessage:
    """
    统一消息格式
    
    所有监听器必须将平台消息转换为此格式。
    """
    id: Optional[str] = None
    listener: str = ""
    platform: str = ""
    type: str = "text"
    content: Any = ""
    user_id: str = ""
    chat_id: str = ""
    thread_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    raw: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "id": self.id,
            "listener": self.listener,
            "platform": self.platform,
            "type": self.type,
            "content": self.content,
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "thread_id": self.thread_id,
            "timestamp": self.timestamp,
            "raw": self.raw
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnifiedMessage":
        """从字典创建消息对象"""
        return cls(
            id=data.get("id"),
            listener=data.get("listener", ""),
            platform=data.get("platform", ""),
            type=data.get("type", "text"),
            content=data.get("content", ""),
            user_id=data.get("user_id", ""),
            chat_id=data.get("chat_id", ""),
            thread_id=data.get("thread_id"),
            timestamp=data.get("timestamp", time.time()),
            raw=data.get("raw")
        )


@dataclass
class OutgoingMessage:
    """
    发送消息格式
    
    核心处理器产生响应后使用此格式发送给监听器。
    """
    listener: str
    chat_id: str
    content: str
    thread_id: Optional[str] = None
    reply_to: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "listener": self.listener,
            "chat_id": self.chat_id,
            "content": self.content,
            "thread_id": self.thread_id,
            "reply_to": self.reply_to
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OutgoingMessage":
        """从字典创建消息对象"""
        return cls(
            listener=data.get("listener", ""),
            chat_id=data.get("chat_id", ""),
            content=data.get("content", ""),
            thread_id=data.get("thread_id"),
            reply_to=data.get("reply_to")
        )


@dataclass
class EventEnvelope:
    """
    事件信封
    
    包装事件数据，包含元信息。
    """
    type: str
    data: Dict[str, Any]
    source: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


class MessageBus:
    """
    消息总线
    
    基于 asyncio.Queue 实现的事件总线，支持发布/订阅模式。
    """
    
    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._handlers: Dict[str, List[Callable[[dict], Awaitable[None]]]] = {}
        self._running: bool = False
        self._stats: Dict[str, int] = {
            "published": 0,
            "dispatched": 0,
            "errors": 0
        }
    
    def subscribe(self, event_type: str, handler: Callable[[dict], Awaitable[None]]) -> None:
        """订阅事件类型"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.debug(f"[MessageBus] 订阅事件: {event_type}, 处理器: {handler.__name__}")
    
    def unsubscribe(self, event_type: str, handler: Callable[[dict], Awaitable[None]]) -> bool:
        """取消订阅事件类型"""
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
                logger.debug(f"[MessageBus] 取消订阅: {event_type}, 处理器: {handler.__name__}")
                return True
            except ValueError:
                pass
        return False
    
    async def publish(self, event_type: str, data: dict, source: str = None) -> None:
        """发布事件到消息总线"""
        envelope = EventEnvelope(
            type=event_type,
            data=data,
            source=source,
            timestamp=time.time()
        )
        await self._queue.put(envelope)
        self._stats["published"] += 1
        logger.debug(f"[MessageBus] 发布事件: {event_type}, 来源: {source}")
    
    async def dispatch_loop(self) -> None:
        """事件分发循环"""
        self._running = True
        logger.info("[MessageBus] 分发循环已启动")
        
        while self._running:
            try:
                envelope: EventEnvelope = await self._queue.get()
                
                handlers = self._handlers.get(envelope.type, [])
                
                if not handlers:
                    logger.debug(f"[MessageBus] 无订阅者: {envelope.type}")
                    continue
                
                for handler in handlers:
                    try:
                        await handler(envelope.data)
                        self._stats["dispatched"] += 1
                    except Exception as e:
                        self._stats["errors"] += 1
                        logger.error(f"[MessageBus] 处理器异常: {handler.__name__}, 错误: {e}")
                
            except asyncio.CancelledError:
                logger.info("[MessageBus] 分发循环被取消")
                break
            except Exception as e:
                logger.error(f"[MessageBus] 分发循环异常: {e}")
        
        logger.info("[MessageBus] 分发循环已停止")
    
    def stop(self) -> None:
        """停止分发循环"""
        self._running = False
    
    @property
    def stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return self._stats.copy()
    
    @property
    def is_running(self) -> bool:
        """检查分发循环是否运行中"""
        return self._running
    
    @property
    def queue_size(self) -> int:
        """获取队列大小"""
        return self._queue.qsize()
