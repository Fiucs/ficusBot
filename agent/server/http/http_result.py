#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
HTTP 响应结果模块

功能说明:
    - 定义 HTTP API 的统一响应格式
    - 提供成功/失败的快捷方法

响应格式:
    {
        "success": true/false,
        "message": "响应消息",
        "data": null 或 {...}
    }
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any, Generic, TypeVar

T = TypeVar("T")


@dataclass
class HttpResult(Generic[T]):
    """
    HTTP 统一响应结果
    
    Attributes:
        success: 请求是否成功
        message: 响应消息
        data: 业务数据
    
    使用示例:
        # 成功响应
        return HttpResult.success("操作成功", data={"id": 1}).to_dict()
        
        # 失败响应
        return HttpResult.error("操作失败").to_dict()
    """
    
    success: bool = True
    message: str = ""
    data: Optional[T] = None
    
    @classmethod
    def success(cls, message: str = "操作成功", data: Optional[T] = None) -> "HttpResult[T]":
        """创建成功响应"""
        return cls(success=True, message=message, data=data)
    
    @classmethod
    def error(cls, message: str = "操作失败", data: Optional[T] = None) -> "HttpResult[T]":
        """创建失败响应"""
        return cls(success=False, message=message, data=data)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，始终包含 success, message, data 三个字段"""
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data
        }
