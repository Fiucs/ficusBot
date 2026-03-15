#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :__init__.py
# @Time      :2026/03/13
# @Author    :Ficus

"""
Watchdog 模块 - 文件监控与热更新

提供文件监控功能，支持：
- MD 记忆文件监控（用户编辑自动同步到向量库）
- 配置文件热加载（独立于记忆系统）
- 工具索引热更新（tool_index.json）
- 写入锁机制（区分 LLM 写入和用户编辑）

Classes:
    FileWatcher: MD 记忆文件监控器
    MemoryEventHandler: MD 文件事件处理器
    ConfigWatcher: 配置文件监控器（独立）
    ConfigEventHandler: 配置文件事件处理器
    ToolIndexWatcher: 工具索引文件监控器

Functions:
    start_file_watcher: 启动 MD 文件监控器
    stop_file_watcher: 停止 MD 文件监控器
    is_file_watcher_enabled: 检查 MD 文件监控是否启用
    start_config_watcher: 启动配置文件监控器
    stop_config_watcher: 停止配置文件监控器
    is_config_watcher_enabled: 检查配置文件监控是否启用
    start_tool_index_watcher: 启动工具索引监控器
    stop_tool_index_watcher: 停止工具索引监控器

Example:
    >>> from agent.watchdog import (
    ...     start_file_watcher,
    ...     stop_file_watcher,
    ...     start_config_watcher,
    ...     stop_config_watcher,
    ...     start_tool_index_watcher,
    ...     stop_tool_index_watcher
    ... )
    >>> from agent.memory.memory_system import MemorySystem
    >>>
    >>> # 启动 MD 文件监控（需要 MemorySystem）
    >>> memory_system = MemorySystem(config)
    >>> start_file_watcher(memory_system)
    >>>
    >>> # 启动配置文件监控（独立，不需要 MemorySystem）
    >>> start_config_watcher()
    >>>
    >>> # 启动工具索引监控
    >>> start_tool_index_watcher()
    >>>
    >>> # ... 运行中 ...
    >>>
    >>> # 停止监控
    >>> stop_file_watcher()
    >>> stop_config_watcher()
    >>> stop_tool_index_watcher()
"""

# MD 文件监控（依赖 MemorySystem）
from agent.watchdog.file_watcher import (
    FileWatcher,
    MemoryEventHandler,
    PollingWatcher,
    WATCHDOG_AVAILABLE,
)
from agent.watchdog.file_watcher_start import (
    start_file_watcher,
    stop_file_watcher,
    get_file_watcher,
    get_all_file_watchers,
    is_file_watcher_enabled,
    is_file_watcher_running,
    get_file_watcher_config,
)

# 配置文件监控（独立）
from agent.watchdog.config_watcher import (
    ConfigWatcher,
    ConfigEventHandler,
    start_config_watcher,
    stop_config_watcher,
    get_config_watcher,
    is_config_watcher_enabled,
    is_config_watcher_running,
    get_config_watcher_config,
)

# 工具索引监控（独立）
from agent.watchdog.tool_index_watcher import (
    ToolIndexWatcher,
    ToolIndexEventHandler,
    start_tool_index_watcher,
    stop_tool_index_watcher,
    get_tool_index_watcher,
    is_tool_index_watcher_running,
    get_tool_index_watcher_config,
    set_agent_instance,
    get_agent_instance,
)

__all__ = [
    # MD 文件监控
    "FileWatcher",
    "MemoryEventHandler",
    "PollingWatcher",
    "WATCHDOG_AVAILABLE",
    "start_file_watcher",
    "stop_file_watcher",
    "get_file_watcher",
    "get_all_file_watchers",
    "is_file_watcher_enabled",
    "is_file_watcher_running",
    "get_file_watcher_config",
    # 配置文件监控
    "ConfigWatcher",
    "ConfigEventHandler",
    "start_config_watcher",
    "stop_config_watcher",
    "get_config_watcher",
    "is_config_watcher_enabled",
    "is_config_watcher_running",
    "get_config_watcher_config",
    # 工具索引监控
    "ToolIndexWatcher",
    "ToolIndexEventHandler",
    "start_tool_index_watcher",
    "stop_tool_index_watcher",
    "get_tool_index_watcher",
    "is_tool_index_watcher_running",
    "get_tool_index_watcher_config",
    "set_agent_instance",
    "get_agent_instance",
]
