#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :router.py
# @Time      :2026/03/02
# @Author    :Ficus

"""
HTTP 拦截路由器模块

功能说明:
    - 定义带拦截器的 FastAPI 路由器
    - 自动对所有路由执行拦截器链
    - 支持链式添加拦截器

核心类:
    - InterceptedRouter: 带拦截器的路由器
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Callable, List
from loguru import logger

from .context import InterceptContext
from ..interceptor.base import Interceptor, InterceptResult


def error_code_to_http_status(error_code: str) -> int:
    """
    错误码转 HTTP 状态码。
    
    参数:
        error_code: 错误码
    
    返回:
        int: HTTP 状态码
    """
    mapping = {
        "FORBIDDEN": 403,
        "UNAUTHORIZED": 401,
        "RATE_LIMITED": 429,
        "BAD_REQUEST": 400,
        "INTERNAL_ERROR": 500,
    }
    return mapping.get(error_code, 500)


class InterceptedRouter(APIRouter):
    """
    带拦截器的路由器
    
    功能说明:
        - 自动对所有路由执行拦截器链
        - 支持链式添加拦截器
        - 区分需要拦截和不需要拦截的路由
    
    核心方法:
        - set_gateway: 设置网关实例
        - use: 添加拦截器
        - api: 注册需要拦截的 API 路由
    
    使用示例:
        router = InterceptedRouter()
        
        # 添加拦截器
        router.use(AuthInterceptor())
        router.use(RateLimitInterceptor())
        
        # 注册路由
        @router.api("/api/chat", methods=["POST"])
        async def chat(ctx: InterceptContext):
            return {"response": ctx.content}
    """
    
    def __init__(self, gateway=None, **kwargs):
        """
        初始化拦截路由器。
        
        参数:
            gateway: Gateway 实例（可选）
            **kwargs: FastAPI APIRouter 参数
        """
        super().__init__(**kwargs)
        self._gateway = gateway
        self._interceptors: List[Interceptor] = []
    
    def set_gateway(self, gateway) -> "InterceptedRouter":
        """
        设置网关实例。
        
        参数:
            gateway: Gateway 实例
        
        返回:
            InterceptedRouter: self
        """
        self._gateway = gateway
        return self
    
    def use(self, interceptor: Interceptor) -> "InterceptedRouter":
        """
        添加拦截器（链式调用）。
        
        参数:
            interceptor: 拦截器实例
        
        返回:
            InterceptedRouter: self
        """
        self._interceptors.append(interceptor)
        logger.debug(
            f"[InterceptedRouter] 添加拦截器: {interceptor.name}"
        )
        return self
    
    async def _execute_interceptors(
        self, 
        request: Request, 
        body: dict
    ) -> InterceptContext:
        """
        执行拦截器链。
        
        参数:
            request: FastAPI Request
            body: 请求体
        
        返回:
            InterceptContext: 拦截后的上下文
        
        抛出:
            HTTPException: 拦截时抛出
        """
        data = {
            "listener": "http",
            "platform": "http",
            "path": request.url.path,
            "method": request.method,
            "user_id": request.headers.get("X-User-ID", "anonymous"),
            "session_id": body.get("session_id", "default"),
            "content": body.get("message", ""),
            "raw": body,
        }
        
        for interceptor in self._interceptors:
            result = await interceptor.intercept(data)
            
            if not result.passed:
                raise HTTPException(
                    status_code=error_code_to_http_status(result.error_code),
                    detail=result.response
                )
            
            if result.data:
                data = result.data
        
        return InterceptContext(
            user_id=data.get("user_id", ""),
            session_id=data.get("session_id", ""),
            content=data.get("content", ""),
            raw=data.get("raw", {}),
            request=request,
        )
    
    def api(self, path: str, methods: List[str] = None, **kwargs):
        """
        注册需要拦截的 API 路由。
        
        参数:
            path: 路由路径
            methods: HTTP 方法列表
            **kwargs: 其他 FastAPI 路由参数
        
        使用示例:
            @router.api("/api/chat", methods=["POST"])
            async def chat(ctx: InterceptContext):
                return {"response": ctx.content}
        """
        methods = methods or ["POST"]
        
        def decorator(func: Callable):
            @self.api_route(path, methods=methods, **kwargs)
            async def wrapper(request: Request):
                body = {}
                if request.method in ["POST", "PUT", "PATCH"]:
                    try:
                        body = await request.json()
                    except Exception:
                        body = {}
                
                ctx = await self._execute_interceptors(request, body)
                return await func(ctx)
            
            return wrapper
        return decorator
