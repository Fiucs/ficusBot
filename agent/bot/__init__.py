#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :__init__.py
# @Time      :2026/03/02
# @Author    :Ficus

"""
Bot 网关模块（向后兼容）

警告:
    此模块已重命名为 agent.server，请使用:
        from agent.server import ...
    
    此模块将在未来版本中移除。
"""

import warnings

# 发出弃用警告
warnings.warn(
    "agent.bot 已弃用，请使用 agent.server",
    DeprecationWarning,
    stacklevel=2
)

# 重导出所有内容
from agent.server import *
from agent.server import (
    MessageBus,
    UnifiedMessage, 
    OutgoingMessage,
    EventEnvelope,
    BaseListener,
    Gateway,
    CoreProcessor,
    EchoProcessor,
    TelegramListener,
    LarkListener,
    DiscordListener,
    get_listener_class,
    InterceptResult,
    Interceptor,
    InterceptorChain,
    AuthInterceptor,
    RateLimitInterceptor,
    SensitiveWordInterceptor,
)

__all__ = [
    "MessageBus",
    "UnifiedMessage", 
    "OutgoingMessage",
    "EventEnvelope",
    "BaseListener",
    "Gateway",
    "CoreProcessor",
    "EchoProcessor",
    "TelegramListener",
    "LarkListener",
    "DiscordListener",
    "get_listener_class",
    "InterceptResult",
    "Interceptor",
    "InterceptorChain",
    "AuthInterceptor",
    "RateLimitInterceptor",
    "SensitiveWordInterceptor",
]
