#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
拦截器模块

功能说明:
    - 提供拦截器基类和拦截器链
    - 提供内置拦截器（权限验证、限流、敏感词过滤）

核心组件:
    - InterceptResult: 拦截结果数据类
    - Interceptor: 拦截器抽象基类
    - InterceptorChain: 拦截器链
    - AuthInterceptor: 权限验证拦截器
    - RateLimitInterceptor: 限流拦截器
    - SensitiveWordInterceptor: 敏感词过滤拦截器
"""

from .base import InterceptResult, Interceptor
from .interceptor_chain import InterceptorChain

__all__ = [
    "InterceptResult",
    "Interceptor",
    "InterceptorChain",
]
