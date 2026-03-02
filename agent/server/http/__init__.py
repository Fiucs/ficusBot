#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :__init__.py
# @Time      :2026/03/02
# @Author    :Ficus

"""
HTTP 模块

功能说明:
    - 提供 FastAPI 应用创建
    - 提供带拦截器的路由器
    - 提供 API 路由定义

核心组件:
    - create_app: 创建 FastAPI 应用
    - InterceptedRouter: 带拦截器的路由器
    - InterceptContext: 拦截上下文
"""

from .app import create_app
from .router import InterceptedRouter
from .context import InterceptContext

__all__ = [
    "create_app",
    "InterceptedRouter",
    "InterceptContext",
]
