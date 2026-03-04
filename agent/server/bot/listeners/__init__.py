#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
平台监听器模块

功能说明:
    - 提供各平台的监听器实现
    - 统一的监听器注册和获取接口
"""

from typing import Dict, Type, Optional
from loguru import logger

from ..base_listener import BaseListener


_LISTENERS: Dict[str, Type[BaseListener]] = {}


def register_listener(platform: str, listener_class: Type[BaseListener]) -> None:
    """注册监听器类"""
    _LISTENERS[platform.lower()] = listener_class
    logger.debug(f"[Listeners] 注册监听器: {platform} -> {listener_class.__name__}")


def get_listener_class(platform: str) -> Optional[Type[BaseListener]]:
    """获取监听器类"""
    return _LISTENERS.get(platform.lower())


def list_available_platforms() -> list:
    """列出所有可用平台"""
    return list(_LISTENERS.keys())


from .telegram import TelegramListener
from .lark import LarkListener
from .discord import DiscordListener
from .qq import QQListener
from .wecom import WeComListener
from .dingtalk import DingTalkListener
from .slack import SlackListener

register_listener("telegram", TelegramListener)
register_listener("feishu", LarkListener)
register_listener("lark", LarkListener)
register_listener("discord", DiscordListener)
register_listener("qq", QQListener)
register_listener("wecom", WeComListener)
register_listener("dingtalk", DingTalkListener)
register_listener("slack", SlackListener)

__all__ = [
    "BaseListener",
    "TelegramListener",
    "LarkListener",
    "DiscordListener",
    "QQListener",
    "WeComListener",
    "DingTalkListener",
    "SlackListener",
    "register_listener",
    "get_listener_class",
    "list_available_platforms",
]
