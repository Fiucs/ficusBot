#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :core_processor.py
# @Time      :2026/02/22
# @Author    :Ficus

"""
核心处理器模块

功能说明:
    - 处理来自监听器的消息
    - 与 Agent 系统集成，调用 LLM 生成响应
    - 将响应发送回对应平台

核心方法:
    - process: 处理 incoming 消息
    - _generate_response: 调用 Agent 生成响应
    - _send_response: 发送响应到消息总线

使用方式:
    processor = CoreProcessor(bus, agent)
    bus.subscribe("incoming", processor.process)
"""

import asyncio
import re
from typing import Dict, Any, Optional, Callable, Awaitable
from loguru import logger

from .message_bus import MessageBus, UnifiedMessage, OutgoingMessage


class CoreProcessor:
    """
    核心处理器
    
    处理来自各平台监听器的消息，调用 Agent 生成响应，
    并将响应发送回对应平台。
    
    功能说明:
        - 订阅 incoming 事件，处理用户消息
        - 调用 Agent 生成响应
        - 发布 outgoing 事件，发送响应
    
    核心方法:
        - process: 处理 incoming 消息
        - set_agent: 设置 Agent 实例
        - add_middleware: 添加消息处理中间件
    
    使用示例:
        processor = CoreProcessor(bus)
        processor.set_agent(agent)
        bus.subscribe("incoming", processor.process)
    """
    
    def __init__(self, bus: MessageBus, agent=None):
        """
        初始化核心处理器。
        
        参数:
            bus: 消息总线实例
            agent: Agent 实例（可选，后续可通过 set_agent 设置）
        """
        self.bus = bus
        self._agent = agent
        self._middlewares: list = []
        self._stats: Dict[str, int] = {
            "processed": 0,
            "responded": 0,
            "errors": 0
        }
        self._session_map: Dict[str, str] = {}
    
    def set_agent(self, agent) -> None:
        """
        设置 Agent 实例。
        
        参数:
            agent: Agent 实例，需实现 chat 方法
        """
        self._agent = agent
        logger.info("[CoreProcessor] Agent 已设置")
    
    def add_middleware(self, middleware: Callable[[UnifiedMessage], Awaitable[Optional[UnifiedMessage]]]) -> None:
        """
        添加消息处理中间件。
        
        中间件可以在消息处理前进行预处理，
        如果返回 None 则跳过该消息。
        
        参数:
            middleware: 异步中间件函数
        """
        self._middlewares.append(middleware)
    
    async def process(self, data: dict) -> None:
        """
        处理 incoming 消息。
        
        处理流程:
            1. 解析消息数据
            2. 执行中间件链
            3. 生成响应
            4. 发送响应
        
        参数:
            data: 消息数据字典
        """
        try:
            message = UnifiedMessage.from_dict(data)
            
            for middleware in self._middlewares:
                result = await middleware(message)
                if result is None:
                    logger.debug(f"[CoreProcessor] 消息被中间件过滤: {message.message_id}")
                    return
                message = result
            
            # 处理不同类型的消息
            logger.info(f"[CoreProcessor] 消息类型: {message.type}, 原始内容: {message.content[:50]}...")
            
            if message.type == "image":
                logger.info(f"[CoreProcessor] 📷 收到图片消息，准备转发给 Agent 处理")
                # 对于图片消息，转换为文本提示
                content = f"[用户发送了一张图片，请回复说：我看到你发送了一张图片，但我目前无法直接查看图片内容。请描述一下图片的内容，或者发送文字消息给我。]"
            elif message.type != "text":
                logger.debug(f"[CoreProcessor] 跳过非文本消息: type={message.type}")
                return
            else:
                content = message.content
            
            self._stats["processed"] += 1
            
            # 使用处理后的 content 生成响应
            response = await self._generate_response_with_content(message, content)
            
            if response:
                await self._send_response(message, response)
                self._stats["responded"] += 1
            
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"[CoreProcessor] 处理消息失败: {e}")
    
    async def _generate_response_with_content(self, message: UnifiedMessage, content: str) -> Optional[str]:
        """
        使用指定内容调用 Agent 生成响应。
        
        参数:
            message: 统一格式消息（用于会话管理）
            content: 要发送给 Agent 的内容
        
        返回:
            Optional[str]: 响应内容，如果生成失败则返回 None
        """
        if not self._agent:
            logger.warning("[CoreProcessor] Agent 未设置，返回默认响应")
            return "🤖 系统正在初始化，请稍后再试..."
        
        try:
            session_key = f"{message.listener}:{message.chat_id}"
            
            if message.thread_id:
                session_key = f"{session_key}:{message.thread_id}"
            
            if session_key not in self._session_map:
                if hasattr(self._agent, 'conversation') and hasattr(self._agent.conversation, 'create_new_session'):
                    session_id = self._agent.conversation.create_new_session()
                    self._session_map[session_key] = session_id
                    logger.debug(f"[CoreProcessor] 创建新会话: {session_key} -> {session_id}")
                else:
                    self._session_map[session_key] = "default"
            else:
                session_id = self._session_map[session_key]
                if hasattr(self._agent, 'conversation') and hasattr(self._agent.conversation, 'switch_session'):
                    self._agent.conversation.switch_session(session_id)
            
            result = self._agent.chat(content)
            
            if isinstance(result, dict):
                response = result.get("content", "")
            else:
                response = str(result)
            
            response = self._clean_response(response)
            
            return response
            
        except Exception as e:
            logger.error(f"[CoreProcessor] 生成响应失败: {e}")
            import traceback
            logger.error(f"[CoreProcessor] 错误堆栈:\n{traceback.format_exc()}")
            return None
    
    async def _generate_response(self, message: UnifiedMessage) -> Optional[str]:
        """
        调用 Agent 生成响应（使用消息原始内容）。
        
        参数:
            message: 统一格式消息
        
        返回:
            Optional[str]: 响应内容，如果生成失败则返回 None
        """
        return await self._generate_response_with_content(message, message.content)
    
    def _clean_response(self, response: str) -> str:
        """
        清理响应内容。
        
        移除可能影响消息显示的特殊标记。
        
        参数:
            response: 原始响应内容
        
        返回:
            str: 清理后的响应内容
        """
        response = re.sub(r'\[/?[a-zA-Z][^\]]*\]', '', response)
        
        return response.strip()
    
    async def _send_response(self, message: UnifiedMessage, response: str) -> None:
        """
        发送响应到消息总线。
        
        参数:
            message: 原始消息
            response: 响应内容
        """
        outgoing = OutgoingMessage(
            listener=message.listener,
            chat_id=message.chat_id,
            content=response,
            thread_id=message.thread_id,
            reply_to=message.id
        )
        
        await self.bus.publish(
            "outgoing",
            outgoing.to_dict(),
            source="core_processor"
        )
        
        logger.debug(
            f"[CoreProcessor] 发送响应: listener={message.listener}, "
            f"chat_id={message.chat_id}"
        )
    
    @property
    def stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return self._stats.copy()


class EchoProcessor:
    """
    回声处理器
    
    简单的测试处理器，将收到的消息原样返回。
    用于测试网关功能，无需 Agent。
    
    使用示例:
        processor = EchoProcessor(bus)
        bus.subscribe("incoming", processor.process)
    """
    
    def __init__(self, bus: MessageBus):
        """
        初始化回声处理器。
        
        参数:
            bus: 消息总线实例
        """
        self.bus = bus
        self._stats = {"processed": 0}
    
    async def process(self, data: dict) -> None:
        """
        处理消息并返回回声。
        
        参数:
            data: 消息数据字典
        """
        message = UnifiedMessage.from_dict(data)
        
        if message.type != "text":
            return
        
        self._stats["processed"] += 1
        
        response = OutgoingMessage(
            listener=message.listener,
            chat_id=message.chat_id,
            content=f"🔊 Echo: {message.content}",
            thread_id=message.thread_id,
            reply_to=message.id
        )
        
        await self.bus.publish("outgoing", response.to_dict())
        
        logger.debug(f"[EchoProcessor] 回声: {message.content[:50]}...")
    
    @property
    def stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return self._stats.copy()
