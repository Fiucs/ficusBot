#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
TinyDB 存储实现模块

功能说明:
    - 基于 TinyDB 实现存储接口
    - 支持查询和索引
    - 自动管理数据库文件
    - 支持中文存储（ensure_ascii=False）

使用示例:
    storage = TinyDBStorage("./data/sessions.json")
    storage.save("session_001", {"history": [...], "metadata": {...}})
    data = storage.load("session_001")
"""

import os
import json
from typing import Dict, List, Any, Optional
from pathlib import Path
from tinydb import TinyDB, Query
from tinydb.storages import JSONStorage
from loguru import logger

from .base_storage import BaseStorage


class UTF8JSONStorage(JSONStorage):
    """
    支持 UTF-8 编码的 JSON 存储类。
    
    功能说明:
        - 继承 TinyDB 的 JSONStorage
        - 使用 ensure_ascii=False 支持中文
        - 使用 indent=2 格式化输出
    
    配置项:
        - encoding: 文件编码，默认 utf-8
        - ensure_ascii: 是否转义非 ASCII 字符，默认 False
        - indent: JSON 缩进，默认 2
    """
    
    def __init__(self, path: str, **kwargs):
        self._encoding = kwargs.pop("encoding", "utf-8")
        self._ensure_ascii = kwargs.pop("ensure_ascii", False)
        self._indent = kwargs.pop("indent", 2)
        super().__init__(path, **kwargs)
    
    def write(self, data: Dict[str, Any]) -> None:
        """写入数据，使用 ensure_ascii=False 支持中文。"""
        self._handle.seek(0)
        serialized = json.dumps(
            data,
            ensure_ascii=self._ensure_ascii,
            indent=self._indent
        )
        self._handle.write(serialized)
        self._handle.flush()
        self._handle.truncate()


class TinyDBStorage(BaseStorage):
    """
    基于 TinyDB 的存储实现。
    
    功能说明:
        - 实现 BaseStorage 接口
        - 支持 JSON 格式存储
        - 支持中文存储（UTF-8 编码）
        - 支持查询功能
        - 自动管理数据库文件
    
    核心方法:
        - save: 保存数据（upsert 模式）
        - load: 加载数据
        - delete: 删除数据
        - query: 查询数据（TinyDB 特有）
    
    配置项:
        - db_path: 数据库文件路径
        - ensure_dir: 是否自动创建目录
    
    使用场景:
        - 会话持久化存储
        - 需要查询功能的存储场景
    """
    
    def __init__(self, db_path: str, ensure_dir: bool = True):
        """
        初始化 TinyDB 存储。
        
        参数:
            db_path: 数据库文件路径
            ensure_dir: 是否自动创建目录，默认 True
        """
        self._db_path = db_path
        
        if ensure_dir:
            db_dir = Path(db_path).parent
            db_dir.mkdir(parents=True, exist_ok=True)
        
        self._db = TinyDB(db_path, storage=UTF8JSONStorage)
        self._query = Query()
        
        logger.debug(f"TinyDBStorage 初始化完成: {db_path}")
    
    @property
    def db(self) -> TinyDB:
        """获取 TinyDB 实例，支持直接查询操作。"""
        return self._db
    
    @property
    def query(self) -> Query:
        """获取 Query 对象，用于复杂查询。"""
        return self._query
    
    def save(self, key: str, data: Dict[str, Any]) -> bool:
        """
        保存数据（upsert 模式）。
        
        参数:
            key: 数据键名（存储为 _key 字段）
            data: 要保存的数据字典
        
        返回:
            bool: 保存是否成功
        """
        try:
            doc = {"_key": key, **data}
            self._db.upsert(doc, self._query._key == key)
            logger.debug(f"TinyDB 保存数据成功: {key}")
            return True
        except Exception as e:
            logger.error(f"TinyDB 保存数据失败: {key}, 错误: {e}")
            return False
    
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """
        加载数据。
        
        参数:
            key: 数据键名
        
        返回:
            Optional[Dict]: 数据字典（不含 _key 字段），不存在则返回 None
        """
        try:
            doc = self._db.get(self._query._key == key)
            if doc:
                data = dict(doc)
                data.pop("_key", None)
                return data
            return None
        except Exception as e:
            logger.error(f"TinyDB 加载数据失败: {key}, 错误: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """
        删除数据。
        
        参数:
            key: 数据键名
        
        返回:
            bool: 删除是否成功
        """
        try:
            removed = self._db.remove(self._query._key == key)
            success = len(removed) > 0
            if success:
                logger.debug(f"TinyDB 删除数据成功: {key}")
            else:
                logger.warning(f"TinyDB 删除数据失败: {key} 不存在")
            return success
        except Exception as e:
            logger.error(f"TinyDB 删除数据失败: {key}, 错误: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """
        检查数据是否存在。
        
        参数:
            key: 数据键名
        
        返回:
            bool: 数据是否存在
        """
        return self._db.contains(self._query._key == key)
    
    def list_all(self) -> List[str]:
        """
        列出所有键名。
        
        返回:
            List[str]: 所有键名列表
        """
        try:
            return [doc["_key"] for doc in self._db.all() if "_key" in doc]
        except Exception as e:
            logger.error(f"TinyDB 列出所有键失败: {e}")
            return []
    
    def clear(self) -> bool:
        """
        清空所有数据。
        
        返回:
            bool: 清空是否成功
        """
        try:
            self._db.truncate()
            logger.debug("TinyDB 清空数据成功")
            return True
        except Exception as e:
            logger.error(f"TinyDB 清空数据失败: {e}")
            return False
    
    def count(self) -> int:
        """
        获取数据总数。
        
        返回:
            int: 数据总数
        """
        return len(self._db)
    
    def search(self, condition) -> List[Dict[str, Any]]:
        """
        按条件查询数据（TinyDB 特有方法）。
        
        参数:
            condition: TinyDB Query 条件
        
        返回:
            List[Dict]: 匹配的数据列表
        """
        try:
            results = self._db.search(condition)
            return [dict(doc) for doc in results]
        except Exception as e:
            logger.error(f"TinyDB 查询失败: {e}")
            return []
    
    def close(self) -> None:
        """关闭数据库连接。"""
        self._db.close()
        logger.debug("TinyDB 连接已关闭")
    
    def __enter__(self):
        """支持上下文管理器。"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文时关闭连接。"""
        self.close()
