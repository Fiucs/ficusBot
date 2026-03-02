#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :base.py
# @Time      :2026/03/02
# @Author    :Ficus

"""
拦截器基类模块

功能说明:
    - 定义拦截器基类和拦截结果数据类
    - 所有拦截器必须继承 Interceptor 基类
    - 拦截结果使用 InterceptResult 统一格式

核心类:
    - InterceptResult: 拦截结果数据类
    - Interceptor: 拦截器抽象基类
"""

from dataclasses import dataclass
from typing import Optional
from abc import ABC, abstractmethod


@dataclass
class InterceptResult:
    """
    拦截结果数据类
    
    用于表示拦截器处理后的结果，包含是否通过、修改后的数据、
    响应消息、拦截原因和错误码等信息。
    
    属性:
        passed: 是否通过（True=继续，False=拦截）
        data: 修改后的数据（可选）
        response: 拦截时的响应消息（可选，用于通知用户）
        reason: 拦截原因（可选，用于日志）
        error_code: 错误码（可选，用于 HTTP 状态码映射）
    """
    passed: bool = True
    data: Optional[dict] = None
    response: Optional[str] = None
    reason: Optional[str] = None
    error_code: Optional[str] = None
    
    @classmethod
    def ok(cls, data: dict = None) -> "InterceptResult":
        """
        创建通过结果。
        
        参数:
            data: 修改后的数据（可选）
        
        返回:
            InterceptResult: 通过结果实例
        """
        return cls(passed=True, data=data)
    
    @classmethod
    def reject(
        cls, 
        response: str = None, 
        reason: str = None, 
        error_code: str = None
    ) -> "InterceptResult":
        """
        创建拦截结果。
        
        参数:
            response: 拦截时的响应消息
            reason: 拦截原因
            error_code: 错误码
        
        返回:
            InterceptResult: 拦截结果实例
        """
        return cls(
            passed=False, 
            response=response, 
            reason=reason, 
            error_code=error_code
        )


class Interceptor(ABC):
    """
    拦截器抽象基类
    
    所有拦截器必须继承此类并实现 intercept 方法。
    拦截器用于在消息处理前进行过滤、验证或修改。
    
    核心方法:
        - name: 拦截器名称属性
        - intercept: 拦截处理方法
    
    使用示例:
        class AuthInterceptor(Interceptor):
            @property
            def name(self) -> str:
                return "auth"
            
            async def intercept(self, data: dict) -> InterceptResult:
                if data.get("user_id") not in self.whitelist:
                    return InterceptResult.reject(
                        response="您没有权限",
                        error_code="FORBIDDEN"
                    )
                return InterceptResult.ok(data)
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """
        拦截器名称。
        
        返回:
            str: 拦截器唯一标识名称
        """
        pass
    
    @abstractmethod
    async def intercept(self, data: dict) -> InterceptResult:
        """
        拦截处理方法。
        
        参数:
            data: 消息数据字典
        
        返回:
            InterceptResult: 拦截结果
        """
        pass
