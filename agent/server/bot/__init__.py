#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
Bot 模块

功能说明:
    - 多平台 Bot 监听器
    - WebSocket 连接管理
    - 消息处理和路由
    - 会话映射管理

核心组件:
    - MessageBus: 消息总线
    - BaseListener: 基础监听器
    - CoreProcessor: 核心处理器
    - EchoProcessor: 回声处理器（测试用）
    - ChatSessionMap: 聊天会话映射

注意:
    Gateway 已移至 server 层，请使用:
    from agent.server import Gateway
"""

from .core_processor import CoreProcessor, EchoProcessor
from .message_bus import MessageBus, UnifiedMessage, OutgoingMessage, EventEnvelope
from .base_listener import BaseListener
from .chat_session_map import ChatSessionMap, ChatSessionInfo

from .listeners import (
    TelegramListener,
    LarkListener,
    DiscordListener,
    QQListener,
    WeComListener,
    DingTalkListener,
    SlackListener,
    get_listener_class,
    list_available_platforms,
)

__all__ = [
    "CoreProcessor",
    "EchoProcessor",
    "MessageBus",
    "UnifiedMessage",
    "OutgoingMessage",
    "EventEnvelope",
    "BaseListener",
    "ChatSessionMap",
    "ChatSessionInfo",
    "TelegramListener",
    "LarkListener",
    "DiscordListener",
    "QQListener",
    "WeComListener",
    "DingTalkListener",
    "SlackListener",
    "get_listener_class",
    "list_available_platforms",
]
