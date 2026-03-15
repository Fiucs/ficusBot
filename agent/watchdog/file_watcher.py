#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :memory_watchdog.py
# @Time      :2026/03/13
# @Author    :Ficus

"""
记忆文件监控模块 - Watchdog 实现

提供文件监控功能，支持：
1. MD 记忆文件监控：用户编辑自动同步到向量库
2. 配置文件热加载：JSON/YAML 文件变更自动重载
3. 写入锁机制：区分 LLM 写入和用户编辑，避免循环触发

核心类:
    FileWatcher: 统一文件监控器，管理所有文件监控
    MemoryEventHandler: MD 文件事件处理器
    ConfigEventHandler: 配置文件事件处理器

使用示例:
    >>> from agent.watchdog import FileWatcher
    >>> from agent.memory.memory_system import MemorySystem
    >>>
    >>> memory_system = MemorySystem(config)
    >>> watcher = FileWatcher(
    ...     memory_system=memory_system,
    ...     config_path="./workspace/config",
    ...     reload_config_callback=lambda path: reload_config(path)
    ... )
    >>> watcher.start()
    >>> # 运行中...
    >>> watcher.stop()
"""

import os
import time
import asyncio
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent, FileDeletedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    # 定义占位类，避免导入错误
    class FileSystemEventHandler:
        pass

from loguru import logger


class MemoryEventHandler(FileSystemEventHandler):
    """
    MD 文件事件处理器
    
    负责监控 MD 记忆文件的变更，区分 LLM 写入和用户编辑：
    - LLM 写入：有锁标记，跳过处理（向量库已更新）
    - 用户编辑：无锁标记，同步到向量库
    
    Attributes:
        memory_system: MemorySystem 实例
        memory_store: MemoryStore 实例
        _processing: 是否正在处理中（防止并发）
        _debounce_timers: 防抖定时器字典
        _executor: 线程池执行器
    """
    
    def __init__(self, memory_system: Any, memory_store: Any):
        """
        初始化 MD 文件事件处理器
        
        Args:
            memory_system: MemorySystem 实例
            memory_store: MemoryStore 实例
        """
        super().__init__()
        self.memory_system = memory_system
        self.memory_store = memory_store
        self._processing = False
        self._debounce_timers: Dict[str, float] = {}
        self._debounce_interval = 0.5  # 防抖间隔（秒）
        self._executor = ThreadPoolExecutor(max_workers=1)  # 单线程执行器
    
    def on_modified(self, event):
        """
        文件修改事件处理
        
        Args:
            event: 文件系统事件
        """
        if event.is_directory:
            return
        
        if not event.src_path.endswith('.md'):
            return
        
        file_name = os.path.basename(event.src_path)
        
        # 防抖检查
        current_time = time.time()
        if file_name in self._debounce_timers:
            if current_time - self._debounce_timers[file_name] < self._debounce_interval:
                return
        self._debounce_timers[file_name] = current_time
        
        # 检查是否是 LLM 写入的（有锁）
        if self.memory_store.is_writing(file_name):
            logger.debug(f"[Watchdog] 跳过 LLM 写入的文件: {file_name}")
            return
        
        # 是用户编辑，使用线程池处理
        logger.info(f"[Watchdog] 检测到用户编辑: {file_name}")
        self._executor.submit(self._handle_user_edit_sync, file_name)
    
    def on_created(self, event):
        """文件创建事件处理"""
        self.on_modified(event)
    
    def on_deleted(self, event):
        """文件删除事件处理"""
        if event.is_directory:
            return
        if not event.src_path.endswith('.md'):
            return
        
        file_name = os.path.basename(event.src_path)
        logger.info(f"[Watchdog] 检测到文件删除: {file_name}")
        self._executor.submit(self._handle_user_edit_sync, file_name)
    
    def _handle_user_edit_sync(self, file_name: str):
        """
        处理用户编辑（同步版本）
        
        检测变动并同步到向量库
        
        Args:
            file_name: 变更的文件名
        """
        if self._processing:
            logger.debug("[Watchdog] 正在处理中，跳过")
            return
        
        self._processing = True
        
        try:
            # 延迟等待文件写入完成
            time.sleep(0.3)
            
            # 检测变动
            changes = self.memory_store.detect_changes()
            
            total_changes = len(changes["added"]) + len(changes["deleted"]) + len(changes["modified"])
            if total_changes == 0:
                logger.debug("[Watchdog] 无变动需要同步")
                return
            
            logger.info(f"[Watchdog] 开始同步用户编辑: 新增={len(changes['added'])}, "
                       f"删除={len(changes['deleted'])}, 修改={len(changes['modified'])}")
            
            # 同步到向量库（同步版本）
            self._sync_to_vector_db_sync(changes)
            
            # 更新索引
            self.memory_store.update_index(changes)
            
            logger.info("[Watchdog] 用户编辑同步完成")
            
        except Exception as e:
            logger.error(f"[Watchdog] 同步用户编辑失败: {e}")
        finally:
            self._processing = False
    
    def _sync_to_vector_db_sync(self, changes: Dict[str, List]):
        """
        同步变动到向量数据库（同步版本）
        
        Args:
            changes: 变更记录 {"added": [], "deleted": [], "modified": []}
        """
        if self.memory_system.memories_table is None:
            logger.warning("[Watchdog] 向量数据库未初始化，跳过同步")
            return
        
        try:
            # 处理新增
            for memory in changes["added"]:
                self._add_memory_to_vector_db_sync(memory)
            
            # 处理删除
            for memory_id in changes["deleted"]:
                self._delete_memory_from_vector_db(memory_id)
            
            # 处理修改
            for memory in changes["modified"]:
                self._update_memory_in_vector_db_sync(memory)
                
        except Exception as e:
            logger.error(f"[Watchdog] 同步到向量库失败: {e}")
            raise
    
    def _add_memory_to_vector_db_sync(self, memory: Dict[str, Any]):
        """
        添加记忆到向量数据库（同步版本）
        
        Args:
            memory: 记忆字典
        """
        try:
            # 使用新的事件循环运行异步嵌入方法
            embedding = asyncio.run(self.memory_system._embed(memory["content"]))
            if not embedding:
                logger.warning(f"[Watchdog] 嵌入计算失败，跳过: {memory['id']}")
                return
            
            entry = {
                "id": memory["id"],
                "content": memory["content"],
                "embedding": embedding,
                "memory_type": memory.get("memory_type", "conversation"),
                "importance": memory.get("importance", 5),
                "tags": memory.get("tags", []),
                "created_at": memory.get("created_at", "")
            }
            
            self.memory_system.memories_table.add([entry])
            logger.debug(f"[Watchdog] 已添加到向量库: {memory['id']}")
            
        except Exception as e:
            logger.error(f"[Watchdog] 添加记忆到向量库失败 {memory['id']}: {e}")
    
    def _delete_memory_from_vector_db(self, memory_id: str):
        """
        从向量数据库删除记忆
        
        Args:
            memory_id: 记忆ID
        """
        try:
            self.memory_system.memories_table.delete(f"id = '{memory_id}'")
            logger.debug(f"[Watchdog] 已从向量库删除: {memory_id}")
        except Exception as e:
            logger.error(f"[Watchdog] 从向量库删除记忆失败 {memory_id}: {e}")
    
    def _update_memory_in_vector_db_sync(self, memory: Dict[str, Any]):
        """
        在向量数据库中更新记忆（先删后插，同步版本）
        
        Args:
            memory: 记忆字典
        """
        try:
            # 先删除旧记录
            self.memory_system.memories_table.delete(f"id = '{memory['id']}'")
            
            # 重新计算 embedding 并插入
            embedding = asyncio.run(self.memory_system._embed(memory["content"]))
            if not embedding:
                logger.warning(f"[Watchdog] 嵌入计算失败，跳过: {memory['id']}")
                return
            
            entry = {
                "id": memory["id"],
                "content": memory["content"],
                "embedding": embedding,
                "memory_type": memory.get("memory_type", "conversation"),
                "importance": memory.get("importance", 5),
                "tags": memory.get("tags", []),
                "created_at": memory.get("created_at", "")
            }
            
            self.memory_system.memories_table.add([entry])
            logger.debug(f"[Watchdog] 已在向量库更新: {memory['id']}")
            
        except Exception as e:
            logger.error(f"[Watchdog] 更新记忆到向量库失败 {memory['id']}: {e}")


class FileWatcher:
    """
    MD 记忆文件监控器

    专门监控 MD 记忆文件变更，用户编辑自动同步到向量库。
    配置文件热加载功能已迁移到 ConfigWatcher 类。

    Attributes:
        memory_system: MemorySystem 实例
        memory_store: MemoryStore 实例
        observer: Watchdog 观察者实例
        _running: 是否正在运行
        _debounce_interval: 防抖间隔（秒）
    """

    def __init__(
        self,
        memory_system: Any,
        debounce_interval: float = 1.0
    ):
        """
        初始化 MD 文件监控器

        Args:
            memory_system: MemorySystem 实例
            debounce_interval: 防抖间隔（秒），默认1秒

        Raises:
            ImportError: 如果 watchdog 库未安装
        """
        if not WATCHDOG_AVAILABLE:
            raise ImportError(
                "watchdog 库未安装，请运行: pip install watchdog"
            )

        self.memory_system = memory_system
        self.memory_store = memory_system.memory_store
        self.debounce_interval = debounce_interval

        self.observer = Observer()
        self._running = False
        self._handler: Optional[MemoryEventHandler] = None

    def start(self):
        """
        启动 MD 文件监控

        开始监控 MD 记忆文件变更
        """
        if self._running:
            logger.warning("[FileWatcher] 监控器已经在运行中")
            return

        try:
            self._start_memory_watching()

            self.observer.start()
            self._running = True
            logger.info("[FileWatcher] MD 文件监控器已启动")

        except Exception as e:
            logger.error(f"[FileWatcher] 启动监控器失败: {e}")
            raise

    def stop(self):
        """
        停止 MD 文件监控

        停止监控并清理资源
        """
        if not self._running:
            return

        try:
            self.observer.stop()
            self.observer.join(timeout=5)
            self._running = False
            self._handler = None
            logger.info("[FileWatcher] MD 文件监控器已停止")
        except Exception as e:
            logger.error(f"[FileWatcher] 停止监控器失败: {e}")

    def _start_memory_watching(self):
        """启动 MD 文件监控"""
        memories_path = self.memory_store.memories_path

        if not memories_path.exists():
            memories_path.mkdir(parents=True, exist_ok=True)

        self._handler = MemoryEventHandler(
            self.memory_system,
            self.memory_store
        )

        self.observer.schedule(self._handler, str(memories_path), recursive=False)
        logger.info(f"[FileWatcher] 开始监控 MD 文件: {memories_path}")
    
    def is_running(self) -> bool:
        """
        检查监控器是否正在运行
        
        Returns:
            是否正在运行
        """
        return self._running


class PollingWatcher:
    """
    轮询式文件监控器（备用方案）
    
    当 watchdog 不可用时使用，通过定时轮询检测文件变更
    
    Attributes:
        memory_system: MemorySystem 实例
        interval: 轮询间隔（秒）
        _running: 是否正在运行
        _task: 轮询任务
    """
    
    def __init__(
        self,
        memory_system: Any,
        interval: float = 5.0
    ):
        """
        初始化轮询监控器
        
        Args:
            memory_system: MemorySystem 实例
            interval: 轮询间隔（秒），默认5秒
        """
        self.memory_system = memory_system
        self.memory_store = memory_system.memory_store
        self.interval = interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    def start(self):
        """启动轮询监控"""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._polling_loop())
        logger.info(f"[PollingWatcher] 轮询监控已启动，间隔: {self.interval}s")
    
    def stop(self):
        """停止轮询监控"""
        if not self._running:
            return
        
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("[PollingWatcher] 轮询监控已停止")
    
    async def _polling_loop(self):
        """轮询循环"""
        while self._running:
            try:
                await self._check_changes()
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[PollingWatcher] 轮询检查失败: {e}")
                await asyncio.sleep(self.interval)
    
    async def _check_changes(self):
        """检查文件变更"""
        changes = self.memory_store.detect_changes()
        
        total_changes = len(changes["added"]) + len(changes["deleted"]) + len(changes["modified"])
        if total_changes == 0:
            return
        
        logger.info(f"[PollingWatcher] 检测到变动: 新增={len(changes['added'])}, "
                   f"删除={len(changes['deleted'])}, 修改={len(changes['modified'])}")
        
        # 同步到向量库
        handler = MemoryEventHandler(self.memory_system, self.memory_store)
        await handler._sync_to_vector_db(changes)
        
        # 更新索引
        self.memory_store.update_index(changes)
        
        logger.info("[PollingWatcher] 同步完成")
    
    def is_running(self) -> bool:
        """
        检查监控器是否正在运行
        
        Returns:
            是否正在运行
        """
        return self._running
