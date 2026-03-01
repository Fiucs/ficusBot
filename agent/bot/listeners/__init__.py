#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :__init__.py
# @Time      :2026/02/22
# @Author    :Ficus

"""
监听器模块

功能说明:
    - 提供各平台的监听器实现
    - 每个监听器使用对应平台的官方 SDK
"""

from .telegram import TelegramListener
from .lark import LarkListener
from .discord import DiscordListener
from .qq import QQListener
from .wecom import WeComListener
from .dingtalk import DingTalkListener
from .slack import SlackListener

__all__ = [
    "TelegramListener",
    "LarkListener",
    "DiscordListener",
    "QQListener",
    "WeComListener",
    "DingTalkListener",
    "SlackListener"
]


def get_listener_class(platform: str):
    """
    根据平台名称获取监听器类。
    
    参数:
        platform: 平台名称（如 "telegram", "lark", "discord", "qq", "wecom", "dingtalk", "slack"）
    
    返回:
        监听器类，如果不存在则返回 None
    """
    listeners = {
        "telegram": TelegramListener,
        "lark": LarkListener,
        "feishu": LarkListener,
        "discord": DiscordListener,
        "qq": QQListener,
        "wecom": WeComListener,
        "dingtalk": DingTalkListener,
        "slack": SlackListener
    }
    return listeners.get(platform.lower())
