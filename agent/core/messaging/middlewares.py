#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :middlewares.py
# @Time      :2026/03/07
# @Author    :Ficus

"""
消息中间件模块

该模块定义消息处理中间件，支持日志、验证、限流等功能。
"""
import time
from abc import ABC, abstractmethod
from typing import Callable, Awaitable, List, Optional
from loguru import logger

from agent.core.messaging.message import Message, MessageResponse


class Middleware(ABC):
    """
    中间件基类
    
    功能说明:
        - 定义中间件接口
        - 支持前置和后置处理
        - 支持中间件链
    
    核心方法:
        - before: 前置处理
        - after: 后置处理
    """
    
    @abstractmethod
    async def before(self, message: Message) -> Optional[MessageResponse]:
        """
        前置处理
        
        Args:
            message: 消息对象
            
        Returns:
            如果返回响应，则中断处理链；返回 None 继续处理
        """
        pass
    
    @abstractmethod
    async def after(
        self, 
        message: Message, 
        response: MessageResponse
    ) -> MessageResponse:
        """
        后置处理
        
        Args:
            message: 消息对象
            response: 响应对象
            
        Returns:
            处理后的响应对象
        """
        pass


class LoggingMiddleware(Middleware):
    """
    日志中间件
    
    功能说明:
        - 记录消息处理日志
        - 记录处理耗时
    """
    
    def __init__(self, log_content: bool = False):
        """
        初始化日志中间件
        
        Args:
            log_content: 是否记录消息内容
        """
        self._log_content = log_content
        self._start_times: dict = {}
    
    async def before(self, message: Message) -> Optional[MessageResponse]:
        """记录消息开始处理"""
        self._start_times[message.id] = time.time()
        
        content_preview = ""
        if self._log_content:
            content_preview = f", 内容: {message.content[:50]}..."
        
        logger.info(
            f"[Middleware] 开始处理消息: {message.id}, "
            f"来源: {message.source.value}, 类型: {message.type.value}{content_preview}"
        )
        return None
    
    async def after(
        self, 
        message: Message, 
        response: MessageResponse
    ) -> MessageResponse:
        """记录消息处理完成"""
        elapsed = time.time() - self._start_times.pop(message.id, time.time())
        
        status = "成功" if response.success else "失败"
        logger.info(
            f"[Middleware] 消息处理完成: {message.id}, "
            f"状态: {status}, 耗时: {elapsed:.2f}s"
        )
        
        response.metadata["elapsed_time"] = elapsed
        return response


class ValidationMiddleware(Middleware):
    """
    验证中间件
    
    功能说明:
        - 验证消息格式
        - 验证必填字段
    """
    
    def __init__(
        self, 
        require_user_id: bool = False,
        require_session_id: bool = False,
        max_content_length: int = 10000
    ):
        """
        初始化验证中间件
        
        Args:
            require_user_id: 是否要求用户ID
            require_session_id: 是否要求会话ID
            max_content_length: 最大内容长度
        """
        self._require_user_id = require_user_id
        self._require_session_id = require_session_id
        self._max_content_length = max_content_length
    
    async def before(self, message: Message) -> Optional[MessageResponse]:
        """验证消息"""
        if not message.content:
            return MessageResponse(
                message_id=message.id,
                success=False,
                error="消息内容不能为空"
            )
        
        if len(message.content) > self._max_content_length:
            return MessageResponse(
                message_id=message.id,
                success=False,
                error=f"消息内容超过最大长度限制: {self._max_content_length}"
            )
        
        if self._require_user_id and not message.user_id:
            return MessageResponse(
                message_id=message.id,
                success=False,
                error="缺少用户ID"
            )
        
        if self._require_session_id and not message.session_id:
            return MessageResponse(
                message_id=message.id,
                success=False,
                error="缺少会话ID"
            )
        
        return None
    
    async def after(
        self, 
        message: Message, 
        response: MessageResponse
    ) -> MessageResponse:
        """后置处理（无操作）"""
        return response


class RateLimitMiddleware(Middleware):
    """
    限流中间件
    
    功能说明:
        - 限制消息处理频率
        - 支持按用户限流
    """
    
    def __init__(
        self, 
        max_requests: int = 100,
        window_seconds: int = 60
    ):
        """
        初始化限流中间件
        
        Args:
            max_requests: 时间窗口内最大请求数
            window_seconds: 时间窗口（秒）
        """
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._request_counts: dict = {}
        self._window_starts: dict = {}
    
    async def before(self, message: Message) -> Optional[MessageResponse]:
        """检查限流"""
        key = message.user_id or "anonymous"
        now = time.time()
        
        if key not in self._window_starts:
            self._window_starts[key] = now
            self._request_counts[key] = 0
        
        window_start = self._window_starts[key]
        
        if now - window_start > self._window_seconds:
            self._window_starts[key] = now
            self._request_counts[key] = 0
        
        self._request_counts[key] += 1
        
        if self._request_counts[key] > self._max_requests:
            return MessageResponse(
                message_id=message.id,
                success=False,
                error="请求过于频繁，请稍后再试"
            )
        
        return None
    
    async def after(
        self, 
        message: Message, 
        response: MessageResponse
    ) -> MessageResponse:
        """后置处理（无操作）"""
        return response


class MiddlewareChain:
    """
    中间件链
    
    功能说明:
        - 管理中间件链
        - 按顺序执行中间件
        - 支持动态添加中间件
    """
    
    def __init__(self):
        """初始化中间件链"""
        self._middlewares: List[Middleware] = []
    
    def add(self, middleware: Middleware) -> "MiddlewareChain":
        """
        添加中间件
        
        Args:
            middleware: 中间件实例
            
        Returns:
            self（支持链式调用）
        """
        self._middlewares.append(middleware)
        return self
    
    def remove(self, middleware: Middleware) -> bool:
        """
        移除中间件
        
        Args:
            middleware: 中间件实例
            
        Returns:
            是否成功移除
        """
        try:
            self._middlewares.remove(middleware)
            return True
        except ValueError:
            return False
    
    async def process(
        self,
        message: Message,
        handler: Callable[[Message], Awaitable[MessageResponse]]
    ) -> MessageResponse:
        """
        执行中间件链
        
        Args:
            message: 消息对象
            handler: 最终处理函数
            
        Returns:
            响应对象
        """
        for middleware in self._middlewares:
            result = await middleware.before(message)
            if result is not None:
                return result
        
        response = await handler(message)
        
        for middleware in reversed(self._middlewares):
            response = await middleware.after(message, response)
        
        return response
    
    @property
    def middlewares(self) -> List[Middleware]:
        """获取中间件列表"""
        return self._middlewares.copy()
