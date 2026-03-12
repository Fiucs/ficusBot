#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :message.py
# @Time      :2026/03/07
# @Author    :Ficus

"""
消息格式定义模块

该模块定义统一消息格式、消息来源枚举和消息类型枚举。
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, AsyncGenerator, Any, Union
import uuid
import time


class MessageSource(str, Enum):
    """
    消息来源枚举
    
    Attributes:
        CLI: 命令行界面
        API: HTTP API
        BOT: Bot 监听器
        TIMER: 定时任务
        PLUGIN: 插件
        EXTERNAL: 外部系统
    """
    CLI = "cli"
    API = "api"
    BOT = "bot"
    TIMER = "timer"
    PLUGIN = "plugin"
    EXTERNAL = "external"


class MessageType(str, Enum):
    """
    消息类型枚举
    
    Attributes:
        CHAT: 聊天消息
        COMMAND: 命令消息
        TASK_TRIGGER: 任务触发消息
        EVENT: 事件消息
    """
    CHAT = "chat"
    COMMAND = "command"
    TASK_TRIGGER = "task_trigger"
    EVENT = "event"


@dataclass
class Message:
    """
    统一消息格式
    
    所有输入源必须将消息转换为此格式。
    
    Attributes:
        id: 消息ID，自动生成UUID
        source: 来源枚举值
        type: 类型枚举值
        content: 消息内容
        images: 图片列表，每项为 URL 或 base64 字符串
        user_id: 用户ID
        session_id: 会话ID
        metadata: 元数据（含路由信息）
        timestamp: 时间戳
    
    路由元数据:
        - target_agent: 单播目标 Agent ID
        - target_agents: 多播目标 Agent ID 列表
        - broadcast: 是否广播到所有 Agent
    
    图片格式:
        - URL 格式: "https://example.com/image.jpg"
        - Base64 格式: "data:image/jpeg;base64,{base64_data}"
    """
    id: str
    source: MessageSource
    type: MessageType
    content: str
    images: List[str] = field(default_factory=list)
    user_id: str = ""
    session_id: Optional[str] = None
    metadata: Dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    
    @classmethod
    def create(
        cls,
        source: MessageSource,
        type: MessageType,
        content: str,
        images: Optional[List[str]] = None,
        **kwargs
    ) -> "Message":
        """
        创建消息实例
        
        Args:
            source: 消息来源
            type: 消息类型
            content: 消息内容
            images: 图片列表（可选）
            **kwargs: 其他参数（user_id, session_id, metadata）
            
        Returns:
            Message 实例
        """
        return cls(
            id=str(uuid.uuid4()),
            source=source,
            type=type,
            content=content,
            images=images or [],
            **kwargs
        )
    
    def to_dict(self) -> Dict:
        """转换为字典格式"""
        return {
            "id": self.id,
            "source": self.source.value if isinstance(self.source, MessageSource) else self.source,
            "type": self.type.value if isinstance(self.type, MessageType) else self.type,
            "content": self.content,
            "images": self.images,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "metadata": self.metadata,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Message":
        """从字典创建消息对象"""
        source = data.get("source", "cli")
        msg_type = data.get("type", "chat")
        
        if isinstance(source, str):
            source = MessageSource(source)
        if isinstance(msg_type, str):
            msg_type = MessageType(msg_type)
        
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            source=source,
            type=msg_type,
            content=data.get("content", ""),
            images=data.get("images", []),
            user_id=data.get("user_id", ""),
            session_id=data.get("session_id"),
            metadata=data.get("metadata", {}),
            timestamp=data.get("timestamp", time.time())
        )


@dataclass
class MessageResponse:
    """
    消息响应格式
    
    处理器处理消息后返回此格式。
    
    Attributes:
        message_id: 原消息ID
        content: 响应内容
        success: 是否成功
        error: 错误信息
        metadata: 元数据
        responses: 多播/广播时的子响应列表
    """
    message_id: str
    content: str = ""
    success: bool = True
    error: Optional[str] = None
    metadata: Dict = field(default_factory=dict)
    responses: Optional[List[Dict]] = None
    
    def to_dict(self) -> Dict:
        """转换为字典格式"""
        return {
            "message_id": self.message_id,
            "content": self.content,
            "success": self.success,
            "error": self.error,
            "metadata": self.metadata,
            "responses": self.responses
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "MessageResponse":
        """从字典创建响应对象"""
        return cls(
            message_id=data.get("message_id", ""),
            content=data.get("content", ""),
            success=data.get("success", True),
            error=data.get("error"),
            metadata=data.get("metadata", {}),
            responses=data.get("responses")
        )
    
    @classmethod
    def error_response(cls, message_id: str, error: str) -> "MessageResponse":
        """
        创建错误响应
        
        Args:
            message_id: 原消息ID
            error: 错误信息
            
        Returns:
            错误响应实例
        """
        return cls(
            message_id=message_id,
            success=False,
            error=error
        )


@dataclass
class StreamResponse:
    """
    流式响应包装对象
    
    用于包装流式生成器，使其能够通过消息层传递，
    同时保留元数据和状态信息。
    
    Attributes:
        message_id: 原消息ID
        generator: 流式数据生成器
        success: 是否成功
        error: 错误信息
        metadata: 元数据（含 agent_id、统计信息等）
    
    使用示例:
        response = await channel.publish_stream(message)
        async for chunk in response.generator:
            yield chunk
    """
    message_id: str
    generator: Optional[AsyncGenerator[str, None]] = None
    success: bool = True
    error: Optional[str] = None
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """转换为字典格式（不包含生成器）"""
        return {
            "message_id": self.message_id,
            "success": self.success,
            "error": self.error,
            "metadata": self.metadata
        }
    
    @classmethod
    def error_response(cls, message_id: str, error: str) -> "StreamResponse":
        """
        创建错误响应
        
        Args:
            message_id: 原消息ID
            error: 错误信息
            
        Returns:
            错误响应实例
        """
        return cls(
            message_id=message_id,
            success=False,
            error=error
        )
