#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :file_watcher_start.py
# @Time      :2026/03/13
# @Author    :Ficus

"""
MD 文件监控启动模块

负责启动和停止 MD 记忆文件监控器。
注意：配置文件热加载功能已迁移到 config_watcher 模块。

功能说明:
    - 读取配置决定是否启动 MD 文件监控
    - 创建并启动 FileWatcher 实例
    - 提供统一的启动/停止接口
    - 支持多 Agent 架构，每个 Agent 独立管理监控器

配置项 (config.json):
    hot_reload.memory_files:
        enabled: 是否启用 MD 文件监控（默认 True）
        polling_interval: 轮询间隔（秒，watchdog 不可用时使用）
        debounce_interval: 防抖间隔（秒）

使用示例:
    >>> from agent.watchdog.file_watcher_start import start_file_watcher, stop_file_watcher
    >>> from agent.memory.memory_system import MemorySystem
    >>>
    >>> memory_system = MemorySystem(config)
    >>> watcher = start_file_watcher(memory_system, agent_id="default")
    >>> # 运行中...
    >>> stop_file_watcher(agent_id="default")  # 停止指定 Agent 的监控器
    >>> stop_file_watcher()  # 停止所有监控器
"""

from typing import Optional, Any, Dict

from loguru import logger

from agent.config.configloader import GLOBAL_CONFIG

# 全局 FileWatcher 实例字典（支持多 Agent）
_file_watcher_instances: Dict[str, Any] = {}


def is_file_watcher_enabled() -> bool:
    """
    检查 MD 文件监控是否启用

    从全局配置中读取 hot_reload.memory_files.enabled 配置项

    Returns:
        是否启用 MD 文件监控（默认 True）
    """
    hot_reload_config = GLOBAL_CONFIG.get("hot_reload", {})
    memory_files_config = hot_reload_config.get("memory_files", {})
    return memory_files_config.get("enabled", True)


def get_file_watcher_config() -> dict:
    """
    获取 MD 文件监控配置

    Returns:
        文件监控配置字典
    """
    default_config = {
        "enabled": True,
        "polling_interval": 5.0,
        "debounce_interval": 1.0
    }

    hot_reload_config = GLOBAL_CONFIG.get("hot_reload", {})
    memory_files_config = hot_reload_config.get("memory_files", {})

    config = default_config.copy()
    config.update(memory_files_config)

    return config


def start_file_watcher(memory_system: Any, agent_id: str = "default") -> Optional[Any]:
    """
    启动 MD 文件监控器（支持多 Agent）

    根据配置决定是否启动 FileWatcher。如果 watchdog 不可用，
    会自动降级为 PollingWatcher。

    Args:
        memory_system: MemorySystem 实例
        agent_id: Agent 唯一标识符，用于区分不同 Agent 的监控器

    Returns:
        FileWatcher 实例，如果未启用或启动失败返回 None
    """
    global _file_watcher_instances

    # 检查该 Agent 的监控器是否已启动
    if agent_id in _file_watcher_instances:
        existing_watcher = _file_watcher_instances[agent_id]
        if existing_watcher is not None and existing_watcher.is_running():
            logger.info(f"[FileWatcher] Agent '{agent_id}' 的 MD 文件监控器已在运行中")
            return existing_watcher

    # 检查是否启用
    if not is_file_watcher_enabled():
        logger.info(f"[FileWatcher] Agent '{agent_id}' MD 文件监控已禁用")
        return None

    # 获取配置
    config = get_file_watcher_config()
    debounce_interval = config.get("debounce_interval", 1.0)

    try:
        # 尝试导入并使用 watchdog
        from agent.watchdog.file_watcher import FileWatcher, WATCHDOG_AVAILABLE

        if WATCHDOG_AVAILABLE:
            watcher = FileWatcher(
                memory_system=memory_system,
                debounce_interval=debounce_interval
            )
            watcher.start()
            _file_watcher_instances[agent_id] = watcher
            logger.info(f"[FileWatcher] Agent '{agent_id}' 使用 Watchdog 模式启动 MD 文件监控")
        else:
            # 降级到轮询模式
            from agent.watchdog.file_watcher import PollingWatcher

            polling_interval = config.get("polling_interval", 5.0)
            watcher = PollingWatcher(
                memory_system=memory_system,
                interval=polling_interval
            )
            watcher.start()
            _file_watcher_instances[agent_id] = watcher
            logger.info(f"[FileWatcher] Agent '{agent_id}' 使用 Polling 模式启动 MD 文件监控（间隔: {polling_interval}s）")

        return watcher

    except ImportError as e:
        logger.warning(f"[FileWatcher] 文件监控模块未安装: {e}")
        logger.warning("[FileWatcher] 请运行: pip install watchdog")
        return None
    except Exception as e:
        logger.error(f"[FileWatcher] Agent '{agent_id}' 启动 MD 文件监控失败: {e}")
        if agent_id in _file_watcher_instances:
            del _file_watcher_instances[agent_id]
        return None


def stop_file_watcher(agent_id: Optional[str] = None) -> bool:
    """
    停止 MD 文件监控器

    Args:
        agent_id: Agent 唯一标识符。如果为 None，停止所有监控器

    Returns:
        是否成功停止
    """
    global _file_watcher_instances

    if agent_id is not None:
        # 停止指定 Agent 的监控器
        if agent_id not in _file_watcher_instances:
            return True

        try:
            watcher = _file_watcher_instances[agent_id]
            watcher.stop()
            del _file_watcher_instances[agent_id]
            logger.info(f"[FileWatcher] Agent '{agent_id}' 的 MD 文件监控器已停止")
            return True
        except Exception as e:
            logger.error(f"[FileWatcher] Agent '{agent_id}' 停止 MD 文件监控器失败: {e}")
            return False
    else:
        # 停止所有监控器
        success = True
        for aid in list(_file_watcher_instances.keys()):
            try:
                watcher = _file_watcher_instances[aid]
                watcher.stop()
                del _file_watcher_instances[aid]
                logger.info(f"[FileWatcher] Agent '{aid}' 的 MD 文件监控器已停止")
            except Exception as e:
                logger.error(f"[FileWatcher] Agent '{aid}' 停止 MD 文件监控器失败: {e}")
                success = False
        return success


def get_file_watcher(agent_id: str = "default") -> Optional[Any]:
    """
    获取指定 Agent 的 FileWatcher 实例

    Args:
        agent_id: Agent 唯一标识符

    Returns:
        FileWatcher 实例，如果未启动返回 None
    """
    return _file_watcher_instances.get(agent_id)


def get_all_file_watchers() -> Dict[str, Any]:
    """
    获取所有 FileWatcher 实例

    Returns:
        FileWatcher 实例字典 {agent_id: watcher}
    """
    return _file_watcher_instances.copy()


def is_file_watcher_running(agent_id: Optional[str] = None) -> bool:
    """
    检查 MD 文件监控器是否正在运行

    Args:
        agent_id: Agent 唯一标识符。如果为 None，检查是否有任何监控器在运行

    Returns:
        是否正在运行
    """
    if agent_id is not None:
        watcher = _file_watcher_instances.get(agent_id)
        if watcher is None:
            return False
        try:
            return watcher.is_running()
        except Exception:
            return False
    else:
        # 检查是否有任何监控器在运行
        for watcher in _file_watcher_instances.values():
            try:
                if watcher.is_running():
                    return True
            except Exception:
                pass
        return False
