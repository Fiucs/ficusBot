#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :__init__.py
# @Time      :2026/03/02
# @Author    :Ficus

"""
内置拦截器模块

功能说明:
    - 提供常用的内置拦截器
    - 权限验证、限流、敏感词过滤

核心组件:
    - AuthInterceptor: 权限验证拦截器
    - RateLimitInterceptor: 限流拦截器
    - SensitiveWordInterceptor: 敏感词过滤拦截器
"""

from .auth import AuthInterceptor
from .rate_limit import RateLimitInterceptor
from .sensitive import SensitiveWordInterceptor

__all__ = [
    "AuthInterceptor",
    "RateLimitInterceptor",
    "SensitiveWordInterceptor",
]
