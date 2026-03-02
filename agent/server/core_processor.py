#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
核心处理器模块

功能说明:
    - 处理来自监听器的消息
    - 与 Agent 系统集成，调用 LLM 生成响应
    - 支持命令处理（/new, /help 等）
    - 会话持久化映射管理

核心方法:
    - process: 处理 incoming 消息
    - _handle_command: 处理命令
    - _generate_response: 调用 Agent 生成响应
    - _send_response: 发送响应到消息总线

使用方式:
    processor = CoreProcessor(bus, agent_registry)
    bus.subscribe("incoming", processor.process)
"""

import re
from typing import Dict, Any, Optional, Callable, Awaitable, TYPE_CHECKING
from loguru import logger

from .message_bus import MessageBus, UnifiedMessage, OutgoingMessage
from .command import CommandHandler, CommandContext, CommandResult
from .session_map import ChatSessionMap, ChatSessionInfo

if TYPE_CHECKING:
    from agent.registry import AgentRegistry
    from agent.main import Agent


class CoreProcessor:
    """
    核心处理器
    
    处理来自各平台监听器的消息，调用 Agent 生成响应，
    并将响应发送回对应平台。
    
    功能说明:
        - 订阅 incoming 事件，处理用户消息
        - 支持命令处理（/new, /help 等）
        - 会话持久化映射（chat_id -> session_id）
        - 调用 Agent 生成响应
        - 发布 outgoing 事件，发送响应
    
    核心方法:
        - process: 处理 incoming 消息
        - set_agent: 设置默认 Agent 实例
        - set_agent_registry: 设置 Agent 注册中心
        - add_middleware: 添加消息处理中间件
    
    使用示例:
        from agent.registry import AGENT_REGISTRY
        
        processor = CoreProcessor(bus, AGENT_REGISTRY)
        bus.subscribe("incoming", processor.process)
    """
    
    def __init__(self, bus: MessageBus, agent=None, agent_registry: "AgentRegistry" = None):
        """
        初始化核心处理器。
        
        Args:
            bus: 消息总线实例
            agent: 默认 Agent 实例（可选，推荐使用 agent_registry）
            agent_registry: Agent 注册中心（支持多 Agent）
        """
        self.bus = bus
        self._agent = agent
        self._registry = agent_registry
        self._middlewares: list = []
        self._stats: Dict[str, int] = {
            "processed": 0,
            "responded": 0,
            "errors": 0,
            "commands": 0
        }
        
        self._command_handler = CommandHandler(agent_registry)
        self._chat_session_map = ChatSessionMap()
        
        logger.info("[CoreProcessor] 初始化完成，已加载命令处理器和会话映射")
    
    def set_agent(self, agent) -> None:
        """
        设置默认 Agent 实例。
        
        Args:
            agent: Agent 实例，需实现 chat 方法
        """
        self._agent = agent
        logger.info("[CoreProcessor] 默认 Agent 已设置")
    
    def set_agent_registry(self, registry: "AgentRegistry") -> None:
        """
        设置 Agent 注册中心。
        
        Args:
            registry: Agent 注册中心实例
        """
        self._registry = registry
        self._command_handler._registry = registry
        logger.info("[CoreProcessor] Agent 注册中心已设置")
    
    def add_middleware(self, middleware: Callable[[UnifiedMessage], Awaitable[Optional[UnifiedMessage]]]) -> None:
        """
        添加消息处理中间件。
        
        中间件可以在消息处理前进行预处理，
        如果返回 None 则跳过该消息。
        
        Args:
            middleware: 异步中间件函数
        """
        self._middlewares.append(middleware)
    
    async def process(self, data: dict) -> None:
        """
        处理 incoming 消息。
        
        处理流程:
            1. 解析消息数据
            2. 执行中间件链
            3. 检查是否为命令
            4. 生成响应
            5. 发送响应
        
        Args:
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
            
            if message.type == "image":
                logger.info(f"[CoreProcessor] 📷 收到图片消息，准备转发给 Agent 处理")
                content = f"[用户发送了一张图片，请回复说：我看到你发送了一张图片，但我目前无法直接查看图片内容。请描述一下图片的内容，或者发送文字消息给我。]"
            elif message.type != "text":
                logger.debug(f"[CoreProcessor] 跳过非文本消息: type={message.type}")
                return
            else:
                content = message.content
            
            self._stats["processed"] += 1
            
            cmd_result = self._handle_command(content, message)
            
            if cmd_result.is_command:
                self._stats["commands"] += 1
                await self._send_response(message, cmd_result.message)
                self._stats["responded"] += 1
                
                if cmd_result.new_session_id:
                    self._update_session_after_new(message, cmd_result.new_session_id)
                elif cmd_result.switched_session_id:
                    self._update_session_after_switch(message, cmd_result.switched_session_id)
                
                return
            
            response = await self._generate_response_with_content(message, content)
            
            if response:
                await self._send_response(message, response)
                self._stats["responded"] += 1
            
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"[CoreProcessor] 处理消息失败: {e}")
    
    def _handle_command(self, content: str, message: UnifiedMessage) -> CommandResult:
        """
        处理命令。
        
        Args:
            content: 消息内容
            message: 统一消息对象
        
        Returns:
            CommandResult: 命令处理结果
        """
        chat_key = self._build_chat_key(message)
        session_info = self._chat_session_map.get(chat_key)
        
        context = CommandContext(
            agent_id=session_info.agent_id if session_info else "default",
            session_id=session_info.session_id if session_info else None,
            chat_id=chat_key
        )
        
        return self._command_handler.handle(content, context)
    
    def _build_chat_key(self, message: UnifiedMessage) -> str:
        """
        构建聊天标识键。
        
        格式: listener:chat_id[:thread_id]
        
        Args:
            message: 统一消息对象
        
        Returns:
            str: 聊天标识键
        """
        key = f"{message.listener}:{message.chat_id}"
        if message.thread_id:
            key = f"{key}:{message.thread_id}"
        return key
    
    def _get_agent(self, agent_id: str = "default") -> Optional["Agent"]:
        """
        获取 Agent 实例。
        
        优先从注册中心获取，否则返回默认 Agent。
        
        Args:
            agent_id: Agent ID
        
        Returns:
            Agent 实例或 None
        """
        if self._registry:
            try:
                return self._registry.get_agent(agent_id)
            except Exception:
                pass
        return self._agent
    
    async def _generate_response_with_content(self, message: UnifiedMessage, content: str) -> Optional[str]:
        """
        使用指定内容调用 Agent 生成响应。
        
        Args:
            message: 统一格式消息（用于会话管理）
            content: 要发送给 Agent 的内容
        
        Returns:
            Optional[str]: 响应内容，如果生成失败则返回 None
        """
        agent = self._agent
        if not agent:
            logger.warning("[CoreProcessor] Agent 未设置，返回默认响应")
            return "🤖 系统正在初始化，请稍后再试..."
        
        try:
            chat_key = self._build_chat_key(message)
            agent_id = agent.agent_id if hasattr(agent, 'agent_id') else "default"
            
            session_info = self._chat_session_map.get(chat_key)
            session_id = session_info.session_id if session_info else None
            
            if hasattr(agent, 'conversation') and hasattr(agent.conversation, 'switch_session'):
                if session_id:
                    success = agent.conversation.switch_session(session_id)
                    if not success:
                        logger.warning(f"[CoreProcessor] 会话 {session_id} 不存在于存储中，将创建新会话")
                        session_id = None
                
                if not session_id:
                    new_session_id = agent.conversation.create_new_session()
                    self._chat_session_map.set_session(
                        chat_key, 
                        new_session_id, 
                        agent_id
                    )
                    logger.info(f"[CoreProcessor] 已创建新会话: {new_session_id}, chat_key: {chat_key}")
            
            result = agent.chat(content)
            
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
            return False
    
    def _update_session_after_new(self, message: UnifiedMessage, new_session_id: str) -> None:
        """
        创建新会话后更新映射。
        
        Args:
            message: 消息对象
            new_session_id: 新会话 ID
        """
        chat_key = self._build_chat_key(message)
        agent_id = self._agent.agent_id if self._agent and hasattr(self._agent, 'agent_id') else "default"
        self._chat_session_map.set_session(chat_key, new_session_id, agent_id)
        logger.debug(f"[CoreProcessor] 更新会话映射: {chat_key} -> {new_session_id}")
    
    def _update_session_after_switch(self, message: UnifiedMessage, switched_session_id: str) -> None:
        """
        切换会话后更新映射。
        
        Args:
            message: 消息对象
            switched_session_id: 切换后的会话 ID
        """
        chat_key = self._build_chat_key(message)
        agent_id = self._agent.agent_id if self._agent and hasattr(self._agent, 'agent_id') else "default"
        self._chat_session_map.update(chat_key, switched_session_id, agent_id)
        logger.debug(f"[CoreProcessor] 更新会话映射: {chat_key} -> {switched_session_id}")
    
    async def _generate_response(self, message: UnifiedMessage) -> Optional[str]:
        """
        调用 Agent 生成响应（使用消息原始内容）。
        
        Args:
            message: 统一格式消息
        
        Returns:
            Optional[str]: 响应内容，如果生成失败则返回 None
        """
        return await self._generate_response_with_content(message, message.content)
    
    def _clean_response(self, response: str) -> str:
        """
        清理响应内容。
        
        移除可能影响消息显示的特殊标记。
        
        Args:
            response: 原始响应内容
        
        Returns:
            str: 清理后的响应内容
        """
        response = re.sub(r'\[/?[a-zA-Z][^\]]*\]', '', response)
        
        return response.strip()
    
    async def _send_response(self, message: UnifiedMessage, response: str) -> None:
        """
        发送响应到消息总线。
        
        Args:
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
    
    @property
    def command_handler(self) -> CommandHandler:
        """获取命令处理器"""
        return self._command_handler
    
    @property
    def chat_session_map(self) -> ChatSessionMap:
        """获取聊天会话映射"""
        return self._chat_session_map


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
        
        Args:
            bus: 消息总线实例
        """
        self.bus = bus
        self._stats = {"processed": 0}
    
    async def process(self, data: dict) -> None:
        """
        处理消息并返回回声。
        
        Args:
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
