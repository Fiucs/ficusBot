#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :__init__.py
# @Time      :2026/03/02
# @Author    :Ficus

"""
HTTP 路由模块

功能说明:
    - 导出所有路由模块
    - chat: 聊天和工具相关路由
    - health: 健康检查路由
    - command: 命令接口路由
"""

from . import chat
from . import health
from . import command

__all__ = ["chat", "health", "command"]
