#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :context.py
# @Time      :2026/03/02
# @Author    :Ficus

"""
HTTP 拦截上下文模块

功能说明:
    - 定义拦截上下文数据类
    - 包含经过拦截器处理后的请求信息

核心类:
    - InterceptContext: 拦截上下文
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional
from fastapi import Request


@dataclass
class InterceptContext:
    """
    拦截上下文
    
    包含经过拦截器处理后的请求信息，用于路由处理函数。
    
    属性:
        user_id: 用户 ID
        session_id: 会话 ID
        content: 消息内容
        images: 图片列表（可选）
        raw: 原始请求数据
        request: FastAPI Request 对象
        metadata: 元数据字典
    """
    user_id: str
    session_id: str
    content: str
    images: Optional[List[str]] = field(default_factory=list)
    raw: dict = field(default_factory=dict)
    request: Optional[Request] = None
    
    @property
    def metadata(self) -> dict:
        """获取元数据（兼容属性访问）"""
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            **self.raw
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        从原始数据中获取值。
        
        参数:
            key: 键名
            default: 默认值
        
        返回:
            Any: 获取的值或默认值
        """
        return self.raw.get(key, default)
