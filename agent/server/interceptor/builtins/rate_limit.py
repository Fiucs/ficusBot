#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :rate_limit.py
# @Time      :2026/03/02
# @Author    :Ficus

"""
限流拦截器模块

功能说明:
    - 基于用户 ID 的滑动窗口限流
    - 可配置最大请求数和时间窗口

核心类:
    - RateLimitInterceptor: 限流拦截器
"""

import time
from ..base import Interceptor, InterceptResult


class RateLimitInterceptor(Interceptor):
    """
    限流拦截器
    
    功能说明:
        - 基于用户 ID 的滑动窗口限流
        - 可配置最大请求数和时间窗口
    
    核心方法:
        - name: 拦截器名称
        - intercept: 执行限流检查
    
    配置示例:
        interceptor = RateLimitInterceptor(
            max_requests=10,  # 最大请求数
            window=60         # 时间窗口（秒）
        )
    """
    
    def __init__(self, max_requests: int = 10, window: int = 60):
        """
        初始化限流拦截器。
        
        参数:
            max_requests: 时间窗口内最大请求数，默认10
            window: 时间窗口（秒），默认60
        """
        self.max_requests = max_requests
        self.window = window
        self._request_counts: dict = {}  # user_id -> [timestamps]
    
    @property
    def name(self) -> str:
        """
        拦截器名称。
        
        返回:
            str: "rate_limit"
        """
        return "rate_limit"
    
    async def intercept(self, data: dict) -> InterceptResult:
        """
        执行限流检查。
        
        使用滑动窗口算法，检查用户在时间窗口内的请求数。
        
        参数:
            data: 消息数据，需包含 user_id 字段
        
        返回:
            InterceptResult: 限流检查结果
        """
        user_id = data.get("user_id", "anonymous")
        now = time.time()
        
        # 初始化或清理过期记录
        if user_id not in self._request_counts:
            self._request_counts[user_id] = []
        
        # 清理过期的请求记录
        self._request_counts[user_id] = [
            t for t in self._request_counts[user_id]
            if now - t < self.window
        ]
        
        # 检查是否超限
        if len(self._request_counts[user_id]) >= self.max_requests:
            retry_after = int(
                self.window - (now - self._request_counts[user_id][0])
            )
            return InterceptResult.reject(
                response=f"⏳ 请求过于频繁，请 {retry_after} 秒后再试",
                reason=f"用户 {user_id} 请求超限",
                error_code="RATE_LIMITED"
            )
        
        # 记录本次请求
        self._request_counts[user_id].append(now)
        return InterceptResult.ok(data)
