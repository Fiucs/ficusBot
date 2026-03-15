#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :tool_index_watcher.py
# @Time      :2026/03/13
# @Author    :Ficus

"""
工具索引文件监控模块

提供 tool_index.json 文件热加载功能。

功能说明:
    - 监控 tool_index.json 文件变更
    - 文件变更时自动调用回调函数重载工具索引
    - 支持防抖处理，避免频繁触发

核心类:
    ToolIndexEventHandler: 工具索引文件事件处理器
    ToolIndexWatcher: 工具索引文件监控器

使用示例:
    >>> from agent.watchdog.tool_index_watcher import ToolIndexWatcher
    >>>
    >>> def reload_tool_index(path):
    ...     print(f"工具索引已更新: {path}")
    ...     # 重新加载工具索引...
    ...
    >>> watcher = ToolIndexWatcher(
    ...     target_file="./workspace/memory/memory_index/tool_index.json",
    ...     reload_callback=reload_tool_index
    ... )
    >>> watcher.start()
    >>> # 运行中...
    >>> watcher.stop()
"""

import os
import time
from pathlib import Path
from typing import Callable, Optional

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    class FileSystemEventHandler:
        pass

from loguru import logger


class ToolIndexEventHandler(FileSystemEventHandler):
    """
    工具索引文件事件处理器

    专门监控 tool_index.json 文件变更并热加载

    Attributes:
        target_file: 目标工具索引文件路径
        reload_callback: 重载回调函数
        _last_reload: 上次重载时间（用于防抖）
        _debounce_interval: 防抖间隔（秒）
    """

    def __init__(
        self,
        target_file: str,
        reload_callback: Callable[[str], None],
        debounce_interval: float = 1.0
    ):
        """
        初始化工具索引文件事件处理器

        Args:
            target_file: 目标工具索引文件路径
            reload_callback: 工具索引变更时的回调函数，接收文件路径参数
            debounce_interval: 防抖间隔（秒），默认1秒
        """
        super().__init__()
        self.target_file = Path(target_file).resolve()
        self.reload_callback = reload_callback
        self._last_reload: float = 0
        self._debounce_interval = debounce_interval

    def on_modified(self, event):
        """
        文件修改事件处理

        Args:
            event: 文件系统事件
        """
        if event.is_directory:
            return

        event_path = Path(event.src_path).resolve()
        if event_path != self.target_file:
            return

        current_time = time.time()

        if current_time - self._last_reload < self._debounce_interval:
            return

        self._last_reload = current_time

        logger.info(f"[ToolIndexWatcher] tool_index.json 变更，热加载")

        try:
            self.reload_callback(str(self.target_file))
            logger.info(f"[ToolIndexWatcher] tool_index.json 热加载完成")
        except Exception as e:
            logger.error(f"[ToolIndexWatcher] tool_index.json 热加载失败: {e}")

    def on_created(self, event):
        """文件创建事件处理"""
        self.on_modified(event)


class ToolIndexWatcher:
    """
    工具索引文件监控器

    专门监控 tool_index.json 文件变更，自动重载工具索引。

    Attributes:
        target_file: 目标工具索引文件路径
        index_dir: 工具索引文件所在目录
        reload_callback: 工具索引重载回调函数
        observer: Watchdog 观察者实例
        _running: 是否正在运行
        _debounce_interval: 防抖间隔（秒）
    """

    def __init__(
        self,
        target_file: str,
        reload_callback: Callable[[str], None],
        debounce_interval: float = 1.0
    ):
        """
        初始化工具索引文件监控器

        Args:
            target_file: 目标工具索引文件路径
            reload_callback: 工具索引变更时的回调函数
            debounce_interval: 防抖间隔（秒），默认1秒

        Raises:
            ImportError: 如果 watchdog 库未安装
        """
        if not WATCHDOG_AVAILABLE:
            raise ImportError(
                "watchdog 库未安装，请运行: pip install watchdog"
            )

        self.target_file = Path(target_file).resolve()
        self.index_dir = self.target_file.parent
        self.reload_callback = reload_callback
        self.debounce_interval = debounce_interval

        self.observer = Observer()
        self._running = False
        self._handler: Optional[ToolIndexEventHandler] = None

    def start(self):
        """
        启动工具索引文件监控

        开始监控 tool_index.json 文件变更
        """
        if self._running:
            logger.warning("[ToolIndexWatcher] 监控器已经在运行中")
            return

        try:
            self._handler = ToolIndexEventHandler(
                str(self.target_file),
                self.reload_callback,
                self.debounce_interval
            )

            self.observer.schedule(
                self._handler,
                str(self.index_dir),
                recursive=False
            )
            self.observer.start()
            self._running = True
            logger.info(f"[ToolIndexWatcher] tool_index.json 监控器已启动: {self.target_file}")

        except Exception as e:
            logger.error(f"[ToolIndexWatcher] 启动监控器失败: {e}")
            raise

    def stop(self):
        """
        停止工具索引文件监控

        停止监控并清理资源
        """
        if not self._running:
            return

        try:
            self.observer.stop()
            self.observer.join(timeout=5)
            self._running = False
            self._handler = None
            logger.info("[ToolIndexWatcher] 工具索引文件监控器已停止")
        except Exception as e:
            logger.error(f"[ToolIndexWatcher] 停止监控器失败: {e}")

    def is_running(self) -> bool:
        """
        检查监控器是否正在运行

        Returns:
            是否正在运行
        """
        return self._running


_tool_index_watcher_instance: Optional[ToolIndexWatcher] = None


def set_agent_instance(agent: "Agent") -> None:
    """
    设置 Agent 实例引用（已废弃，保留兼容性）

    注意： 此方法已废弃，现在使用 AgentRegistry 管理多 Agent。
    稡块启动时会自动从 AgentRegistry 获取所有 Agent 实例。

    Args:
        agent: Agent 实例
    """
    pass


def get_agent_instance() -> Optional["Agent"]:
    """
    获取当前的 Agent 实例（已废弃，保留兼容性）

    注意: 此方法已废弃。 现在使用 AgentRegistry 管理多 Agent。
    请使用 agent.registry.AGENT_REGISTRY 获取 Agent 实例。

    Returns:
        Agent 实例，如果未设置返回 None
    """
    from agent.registry import AGENT_REGISTRY
    agents = list(AGENT_REGISTRY._agents.values())
    return agents[0] if agents else None


def _hot_reload_tools(file_path: str) -> None:
    """
    热更新工具索引（支持多 Agent）

    当 tool_index.json 变更时， 重新加载所有已创建 Agent 的工具配置。

    Args:
        file_path: 变更的文件路径
    """
    try:
        logger.info(f"[ToolIndexWatcher] 开始热更新工具索引: {file_path}")

        
        from agent.registry import AGENT_REGISTRY
        from agent.core.agent_initializer import AgentInitializer
        import asyncio

        reloaded_count = 0
        
        for agent_id in list(AGENT_REGISTRY._agents.keys()):
            agent = AGENT_REGISTRY._agents.get(agent_id)
            if agent is None:
                continue
            
            if agent.memory_system is None:
                logger.debug(f"[ToolIndexWatcher] Agent '{agent_id}' 记忆系统未启用，跳过")
                continue

            try:
                all_tools = agent.tool_adapter.list_tools()
                result = agent.memory_system.process_tools(all_tools)
                memory_tools = result.get("memory_tools", [])
                keep_tools = result.get("keep_tools", [])

                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(
                            agent.memory_system.sync_memory_tools(memory_tools)
                        )
                    else:
                        loop.run_until_complete(
                            agent.memory_system.sync_memory_tools(memory_tools)
                        )
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(
                            agent.memory_system.sync_memory_tools(memory_tools)
                        )
                    finally:
                        loop.close()

                memory_tool_names = {t.get("function", t).get("name") for t in memory_tools}

                for tool_name in memory_tool_names:
                    if tool_name in agent.tool_adapter.tools:
                        del agent.tool_adapter.tools[tool_name]
                        logger.debug(f"[ToolIndexWatcher] Agent '{agent_id}' 从工具列表移除: {tool_name}")

                agent.tool_adapter._core_tool_names_cache = None

                AgentInitializer._update_injected_skill_list(agent, memory_tool_names)

                reloaded_count += 1
                logger.info(f"[ToolIndexWatcher] Agent '{agent_id}' 工具索引已更新")
                
            except Exception as e:
                logger.error(f"[ToolIndexWatcher] Agent '{agent_id}' 热更新失败: {e}")

        if reloaded_count > 0:
            logger.info(f"[ToolIndexWatcher] ✅ 工具索引热更新完成， 共更新 {reloaded_count} 个 Agent")
        else:
            logger.info("[ToolIndexWatcher] 暂无需要热更新的 Agent")

    except Exception as e:
        logger.error(f"[ToolIndexWatcher] 热更新失败: {e}")


def get_tool_index_watcher_config() -> dict:
    """
    获取工具索引监控配置

    Returns:
        配置字典
    """
    from agent.config.configloader import GLOBAL_CONFIG

    default_config = {
        "enabled": True,
        "debounce_interval": 1.0
    }

    hot_reload_config = GLOBAL_CONFIG.get("hot_reload", {})
    tool_index_config = hot_reload_config.get("tool_index", {})
    config = default_config.copy()
    config.update(tool_index_config)

    return config


def start_tool_index_watcher(
    target_file: Optional[str] = None,
    reload_callback: Optional[Callable[[str], None]] = None
) -> Optional[ToolIndexWatcher]:
    """
    启动工具索引文件监控器

    Args:
        target_file: 目标工具索引文件路径，默认监控 tool_index.json
        reload_callback: 工具索引变更时的回调函数

    Returns:
        ToolIndexWatcher 实例，如果未启用或启动失败返回 None
    """
    global _tool_index_watcher_instance

    if _tool_index_watcher_instance is not None and _tool_index_watcher_instance.is_running():
        logger.info("[ToolIndexWatcher] 监控器已在运行中")
        return _tool_index_watcher_instance

    config = get_tool_index_watcher_config()

    if not config.get("enabled", True):
        logger.info("[ToolIndexWatcher] 工具索引监控已禁用")
        return None

    debounce_interval = config.get("debounce_interval", 1.0)

    if target_file is None:
        from agent.config.configloader import GLOBAL_CONFIG
        workspace_root = GLOBAL_CONFIG.get("workspace_root", ".ficsbot/workspace")
        target_file = Path(workspace_root) / "memory" / "memory_index" / "tool_index.json"

    try:
        if reload_callback is None:
            reload_callback = _hot_reload_tools

        _tool_index_watcher_instance = ToolIndexWatcher(
            target_file=str(target_file),
            reload_callback=reload_callback,
            debounce_interval=debounce_interval
        )
        _tool_index_watcher_instance.start()

        return _tool_index_watcher_instance

    except ImportError as e:
        logger.warning(f"[ToolIndexWatcher] watchdog 库未安装: {e}")
        return None
    except Exception as e:
        logger.error(f"[ToolIndexWatcher] 启动失败: {e}")
        _tool_index_watcher_instance = None
        return None


def stop_tool_index_watcher() -> bool:
    """
    停止工具索引文件监控器

    Returns:
        是否成功停止
    """
    global _tool_index_watcher_instance

    if _tool_index_watcher_instance is None:
        return True

    try:
        _tool_index_watcher_instance.stop()
        _tool_index_watcher_instance = None
        logger.info("[ToolIndexWatcher] 工具索引文件监控器已停止")
        return True
    except Exception as e:
        logger.error(f"[ToolIndexWatcher] 停止失败: {e}")
        return False


def get_tool_index_watcher() -> Optional[ToolIndexWatcher]:
    """
    获取当前的 ToolIndexWatcher 实例

    Returns:
        ToolIndexWatcher 实例，如果未启动返回 None
    """
    return _tool_index_watcher_instance


def is_tool_index_watcher_running() -> bool:
    """
    检查工具索引文件监控器是否正在运行

    Returns:
        是否正在运行
    """
    if _tool_index_watcher_instance is None:
        return False

    try:
        return _tool_index_watcher_instance.is_running()
    except Exception:
        return False
