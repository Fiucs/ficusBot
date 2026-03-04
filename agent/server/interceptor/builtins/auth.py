#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
权限验证拦截器模块

功能说明:
    - 白名单检查：只允许白名单用户
    - 黑名单检查：拒绝黑名单用户

核心类:
    - AuthInterceptor: 权限验证拦截器
"""

from loguru import logger
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
        logger.debug(
            f"[{self.name}] 初始化 | 白名单: {len(self.whitelist)} 人 | "
            f"黑名单: {len(self.blacklist)} 人"
        )
    
    @property
    def name(self) -> str:
        """拦截器名称"""
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
        platform = data.get("platform", "unknown")
        
        # 黑名单检查
        if user_id in self.blacklist:
            logger.info(
                f"[{self.name}] 拦截 | 平台: {platform} | "
                f"用户: {user_id} | 原因: 黑名单用户"
            )
            return InterceptResult.reject(
                response="⛔ 您已被禁止使用此服务",
                reason=f"用户 {user_id} 在黑名单中",
                error_code="FORBIDDEN"
            )
        
        # 白名单检查（如果配置了白名单）
        if self.whitelist and user_id not in self.whitelist:
            logger.info(
                f"[{self.name}] 拦截 | 平台: {platform} | "
                f"用户: {user_id} | 原因: 不在白名单"
            )
            return InterceptResult.reject(
                response="⛔ 抱歉，您没有使用权限",
                reason=f"用户 {user_id} 不在白名单中",
                error_code="FORBIDDEN"
            )
        logger.info(f"[{self.name}] 通过 | 平台: {platform} | 用户: {user_id}, 消息: {data}")
               
        
        return InterceptResult.ok(data)
