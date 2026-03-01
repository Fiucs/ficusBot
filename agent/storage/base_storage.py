#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
存储基类模块

功能说明:
    - 定义统一的存储接口
    - 支持多种存储后端扩展
    - 提供基本的 CRUD 操作抽象

使用示例:
    class MyStorage(BaseStorage):
        def save(self, key: str, data: dict) -> bool:
            # 实现保存逻辑
            pass
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional


class BaseStorage(ABC):
    """
    存储基类，定义通用存储接口。
    
    功能说明:
        - 定义统一的 CRUD 操作接口
        - 支持多种存储后端（文件、数据库等）
        - 提供基础的错误处理
    
    核心方法:
        - save: 保存数据
        - load: 加载数据
        - delete: 删除数据
        - exists: 检查数据是否存在
        - list_all: 列出所有键
        - clear: 清空所有数据
    
    使用场景:
        - 会话持久化
        - 配置存储
        - 缓存管理
    """
    
    @abstractmethod
    def save(self, key: str, data: Dict[str, Any]) -> bool:
        """
        保存数据。
        
        参数:
            key: 数据键名
            data: 要保存的数据字典
        
        返回:
            bool: 保存是否成功
        """
        pass
    
    @abstractmethod
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """
        加载数据。
        
        参数:
            key: 数据键名
        
        返回:
            Optional[Dict]: 数据字典，不存在则返回 None
        """
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """
        删除数据。
        
        参数:
            key: 数据键名
        
        返回:
            bool: 删除是否成功
        """
        pass
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        """
        检查数据是否存在。
        
        参数:
            key: 数据键名
        
        返回:
            bool: 数据是否存在
        """
        pass
    
    @abstractmethod
    def list_all(self) -> List[str]:
        """
        列出所有键名。
        
        返回:
            List[str]: 所有键名列表
        """
        pass
    
    @abstractmethod
    def clear(self) -> bool:
        """
        清空所有数据。
        
        返回:
            bool: 清空是否成功
        """
        pass
    
    @abstractmethod
    def count(self) -> int:
        """
        获取数据总数。
        
        返回:
            int: 数据总数
        """
        pass
