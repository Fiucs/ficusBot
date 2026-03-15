#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :shutdown.py
# @Time      :2026/03/14
# @Author    :Ficus

"""
全局关闭管理模块

功能说明:
    - 提供全局 shutdown 标志
    - 支持优雅关闭和强制关闭
    - 所有长时间运行的操作应检查此标志

使用示例:
    >>> from agent.utils.shutdown import is_shutting_down, shutdown
    >>> if not is_shutting_down():
    ...     # 执行长时间操作
    >>> shutdown()  # 触发关闭
"""

import threading
from typing import Callable, List
from loguru import logger


class ShutdownManager:
    """
    全局关闭管理器
    
    功能说明:
        - 管理全局 shutdown 标志
        - 支持注册关闭回调
        - 线程安全
    
    核心方法:
        - is_shutting_down: 检查是否正在关闭
        - shutdown: 触发关闭
        - register_callback: 注册关闭回调
        - reset: 重置状态（用于测试）
    
    配置项:
        - _shutting_down: 关闭标志
        - _callbacks: 关闭回调列表
        - _lock: 线程锁
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._shutting_down = False
                    cls._instance._callbacks: List[Callable] = []
                    cls._instance._callback_lock = threading.Lock()
        return cls._instance
    
    def is_shutting_down(self) -> bool:
        """检查是否正在关闭"""
        return self._shutting_down
    
    def shutdown(self, reason: str = "User requested") -> None:
        """
        触发关闭
        
        Args:
            reason: 关闭原因
        """
        if self._shutting_down:
            return
        
        with self._lock:
            if self._shutting_down:
                return
            self._shutting_down = True
            logger.info(f"[ShutdownManager] 触发关闭: {reason}")
        
        with self._callback_lock:
            for callback in self._callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"[ShutdownManager] 回调执行失败: {e}")
    
    def register_callback(self, callback: Callable) -> None:
        """
        注册关闭回调
        
        Args:
            callback: 回调函数
        """
        with self._callback_lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)
    
    def reset(self) -> None:
        """重置状态（用于测试）"""
        with self._lock:
            self._shutting_down = False
        with self._callback_lock:
            self._callbacks.clear()


_shutdown_manager = ShutdownManager()


def is_shutting_down() -> bool:
    """检查是否正在关闭"""
    return _shutdown_manager.is_shutting_down()


def shutdown(reason: str = "User requested") -> None:
    """触发关闭"""
    _shutdown_manager.shutdown(reason)


def register_shutdown_callback(callback: Callable) -> None:
    """注册关闭回调"""
    _shutdown_manager.register_callback(callback)


def reset_shutdown_state() -> None:
    """重置关闭状态（用于测试）"""
    _shutdown_manager.reset()
