#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :auth.py
# @Time      :2026/03/02
# @Author    :Ficus

"""
权限验证拦截器模块

功能说明:
    - 白名单检查：只允许白名单用户
    - 黑名单检查：拒绝黑名单用户

核心类:
    - AuthInterceptor: 权限验证拦截器
"""

from ..base import Interceptor, InterceptResult


class AuthInterceptor(Interceptor):
    """
    权限验证拦截器
    
    功能说明:
        - 白名单检查：只允许白名单用户
        - 黑名单检查：拒绝黑名单用户
    
    核心方法:
        - name: 拦截器名称
        - intercept: 执行权限验证
    
    配置示例:
        interceptor = AuthInterceptor(
            whitelist=["user_123", "user_456"],
            blacklist=["user_999"]
        )
    """
    
    def __init__(
        self, 
        whitelist: list = None, 
        blacklist: list = None
    ):
        """
        初始化权限验证拦截器。
        
        参数:
            whitelist: 白名单用户ID列表
            blacklist: 黑名单用户ID列表
        """
        self.whitelist = whitelist or []
        self.blacklist = blacklist or []
    
    @property
    def name(self) -> str:
        """
        拦截器名称。
        
        返回:
            str: "auth"
        """
        return "auth"
    
    async def intercept(self, data: dict) -> InterceptResult:
        """
        执行权限验证。
        
        检查顺序：
        1. 先检查黑名单
        2. 再检查白名单（如果配置了）
        
        参数:
            data: 消息数据，需包含 user_id 字段
        
        返回:
            InterceptResult: 验证结果
        """
        user_id = data.get("user_id", "")
        
        # 黑名单检查
        if user_id in self.blacklist:
            return InterceptResult.reject(
                response="⛔ 您已被禁止使用此服务",
                reason=f"用户 {user_id} 在黑名单中",
                error_code="FORBIDDEN"
            )
        
        # 白名单检查（如果配置了白名单）
        if self.whitelist and user_id not in self.whitelist:
            return InterceptResult.reject(
                response="⛔ 抱歉，您没有使用权限",
                reason=f"用户 {user_id} 不在白名单中",
                error_code="FORBIDDEN"
            )
        
        return InterceptResult.ok(data)
