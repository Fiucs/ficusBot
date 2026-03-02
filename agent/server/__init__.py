#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :__init__.py
# @Time      :2026/02/22
# @Author    :Ficus

"""
Server 服务模块

功能说明:
    - 提供可扩展的多平台机器人网关
    - 支持多种聊天平台（Telegram、飞书、Discord等）
    - 统一消息格式，解耦监听器与核心处理器
    - 提供拦截器系统，支持消息过滤和修改
    - 提供 HTTP API 服务

核心组件:
    - MessageBus: 消息总线
    - BaseListener: 基础监听器接口
    - Gateway: 网关主程序
    - CoreProcessor: 核心处理器
    - EchoProcessor: 回声处理器（测试用）
    - InterceptorChain: 拦截器链
    - Interceptor: 拦截器基类
    - InterceptResult: 拦截结果
"""

from .message_bus import MessageBus, UnifiedMessage, OutgoingMessage, EventEnvelope
from .base_listener import BaseListener
from .gateway import Gateway
from .core_processor import CoreProcessor, EchoProcessor
from .listeners import (
    TelegramListener,
    LarkListener,
    DiscordListener,
    get_listener_class
)
from .interceptor import (
    InterceptResult,
    Interceptor,
    InterceptorChain,
)
from .interceptor.builtins import (
    AuthInterceptor,
    RateLimitInterceptor,
    SensitiveWordInterceptor,
)

__all__ = [
    # 消息相关
    "MessageBus",
    "UnifiedMessage", 
    "OutgoingMessage",
    "EventEnvelope",
    # 监听器相关
    "BaseListener",
    "Gateway",
    "CoreProcessor",
    "EchoProcessor",
    "TelegramListener",
    "LarkListener",
    "DiscordListener",
    "get_listener_class",
    # 拦截器相关
    "InterceptResult",
    "Interceptor",
    "InterceptorChain",
    "AuthInterceptor",
    "RateLimitInterceptor",
    "SensitiveWordInterceptor",
]
