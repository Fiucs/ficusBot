#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :__init__.py
# @Time      :2026/03/07
# @Author    :Ficus

"""
消息层模块

该模块提供统一的消息层功能，支持发布/订阅模式和多 Agent 路由。

核心组件:
    - Message: 统一消息格式
    - MessageResponse: 消息响应格式
    - MessageSource: 消息来源枚举
    - MessageType: 消息类型枚举
    - MessageChannel: 消息通道
    - MessageDispatcher: 消息分发器
    - ChatHandler: 对话处理器
    - CommandHandler: 命令处理器
    - TimerHandler: 定时任务处理器
    - Application: 应用程序单例
    - get_channel: 获取全局通道

使用示例:
    from agent.core.messaging import Message, MessageSource, MessageType, get_channel
    
    # 创建消息
    message = Message.create(
        source=MessageSource.CLI,
        type=MessageType.CHAT,
        content="你好",
        metadata={"target_agent": "default"}
    )
    
    # 发布消息
    response = await get_channel().publish(message, wait_for_response=True)
"""

from agent.core.messaging.message import (
    Message,
    MessageResponse,
    MessageSource,
    MessageType,
)

from agent.core.messaging.channel import MessageChannel

from agent.core.messaging.dispatcher import MessageDispatcher

from agent.core.messaging.handlers import (
    ChatHandler,
    CommandHandler,
)

from agent.core.messaging.middlewares import (
    Middleware,
    LoggingMiddleware,
    ValidationMiddleware,
    RateLimitMiddleware,
    MiddlewareChain,
)

from agent.core.messaging.application import (
    Application,
    get_channel,
    get_application,
)


__all__ = [
    "Message",
    "MessageResponse",
    "MessageSource",
    "MessageType",
    "MessageChannel",
    "MessageDispatcher",
    "ChatHandler",
    "CommandHandler",
    "Middleware",
    "LoggingMiddleware",
    "ValidationMiddleware",
    "RateLimitMiddleware",
    "MiddlewareChain",
    "Application",
    "get_channel",
    "get_application",
]
