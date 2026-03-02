#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :chain.py
# @Time      :2026/03/02
# @Author    :Ficus

"""
拦截器链模块

功能说明:
    - 管理和执行一组拦截器
    - 独立于 MessageBus，作为独立组件
    - 支持链式添加拦截器
    - 按顺序执行拦截器，支持中断和继续

核心类:
    - InterceptorChain: 拦截器链管理类
"""

from typing import List
from loguru import logger

from .base import Interceptor, InterceptResult


class InterceptorChain:
    """
    拦截器链
    
    管理和执行一组拦截器，独立于 MessageBus。
    
    功能说明:
        - 链式添加拦截器
        - 按顺序执行拦截器
        - 支持中断和继续
    
    核心方法:
        - add: 添加拦截器（链式调用）
        - clear: 清空拦截器链
        - execute: 执行拦截器链
    
    使用示例:
        chain = InterceptorChain()
        chain.add(AuthInterceptor()).add(RateLimitInterceptor()).add(SensitiveWordInterceptor())
        
        result = await chain.execute(data)
        if result.passed:
            # 继续处理
        else:
            # 拦截，发送响应
    """
    
    def __init__(self):
        """初始化拦截器链。"""
        self._interceptors: List[Interceptor] = []
    
    def add(self, interceptor: Interceptor) -> "InterceptorChain":
        """
        添加拦截器（链式调用）。
        
        参数:
            interceptor: 拦截器实例
        
        返回:
            InterceptorChain: self，支持链式调用
        """
        self._interceptors.append(interceptor)
        logger.debug(f"[InterceptorChain] 添加拦截器: {interceptor.name}")
        return self
    
    def clear(self) -> None:
        """清空拦截器链。"""
        self._interceptors.clear()
        logger.debug("[InterceptorChain] 已清空拦截器链")
    
    async def execute(self, data: dict) -> InterceptResult:
        """
        执行拦截器链。
        
        按顺序执行所有拦截器，如果某个拦截器返回 reject，
        则中断执行并返回该结果。
        
        参数:
            data: 消息数据
        
        返回:
            InterceptResult: 最终结果
                - passed=True: 所有拦截器通过
                - passed=False: 被某个拦截器拦截
        """
        current_data = data
        
        for interceptor in self._interceptors:
            try:
                result = await interceptor.intercept(current_data)
                
                if not result.passed:
                    logger.info(
                        f"[InterceptorChain] 被 {interceptor.name} 拦截: {result.reason}"
                    )
                    return result
                
                if result.data:
                    current_data = result.data
                    
            except Exception as e:
                logger.error(
                    f"[InterceptorChain] {interceptor.name} 执行异常: {e}"
                )
                return InterceptResult.reject(
                    response="系统错误，请稍后重试",
                    reason=f"拦截器异常: {e}",
                    error_code="INTERNAL_ERROR"
                )
        
        return InterceptResult.ok(current_data)
    
    @property
    def interceptors(self) -> List[Interceptor]:
        """
        获取拦截器列表副本。
        
        返回:
            List[Interceptor]: 拦截器列表
        """
        return self._interceptors.copy()
    
    @property
    def count(self) -> int:
        """
        获取拦截器数量。
        
        返回:
            int: 拦截器数量
        """
        return len(self._interceptors)
