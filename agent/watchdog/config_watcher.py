#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :config_watcher.py
# @Time      :2026/03/13
# @Author    :Ficus

"""
配置文件监控模块 - 独立实现

提供配置文件热加载功能，不依赖记忆系统。

功能说明:
    - 监控 JSON/YAML/TOML/INI/MD 配置文件变更
    - 支持同时监控多个文件
    - 文件变更时自动调用回调函数
    - 支持防抖处理，避免频繁触发

核心类:
    ConfigEventHandler: 配置文件事件处理器
    ConfigWatcher: 配置文件监控器

使用示例:
    >>> from agent.watchdog.config_watcher import ConfigWatcher
    >>>
    >>> def reload_config(path):
    ...     print(f"配置文件已更新: {path}")
    ...     # 重新加载配置...
    ...
    >>> # 单文件监控
    >>> watcher = ConfigWatcher(
    ...     target_file="./workspace/config.json",
    ...     reload_callback=reload_config
    ... )
    >>> watcher.start()
    >>>
    >>> # 多文件监控
    >>> watcher = ConfigWatcher()
    >>> watcher.add_file("./config.json", reload_config)
    >>> watcher.add_file("./agents.md", reload_agents)
    >>> watcher.start()
"""

import os
import time
from pathlib import Path
from typing import Callable, Dict, Optional

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    # 定义占位类，避免导入错误
    class FileSystemEventHandler:
        pass

from loguru import logger


class ConfigEventHandler(FileSystemEventHandler):
    """
    配置文件事件处理器

    支持监控多个文件变更并热加载

    Attributes:
        _target_files: 目标文件路径到回调函数的映射
        _last_reload_map: 各文件上次重载时间（用于防抖）
        _debounce_interval: 防抖间隔（秒）
    """

    def __init__(self, debounce_interval: float = 1.0):
        """
        初始化配置文件事件处理器

        Args:
            debounce_interval: 防抖间隔（秒），默认1秒
        """
        super().__init__()
        self._target_files: Dict[Path, Callable[[str], None]] = {}
        self._last_reload_map: Dict[Path, float] = {}
        self._debounce_interval = debounce_interval

    def add_file(
        self,
        target_file: str,
        reload_callback: Callable[[str], None]
    ) -> None:
        """
        添加要监控的文件

        Args:
            target_file: 目标文件路径
            reload_callback: 文件变更时的回调函数，接收文件路径参数
        """
        file_path = Path(target_file).resolve()
        self._target_files[file_path] = reload_callback
        self._last_reload_map[file_path] = 0
        logger.debug(f"[ConfigEventHandler] 添加文件监控: {file_path}")

    def remove_file(self, target_file: str) -> bool:
        """
        移除文件监控

        Args:
            target_file: 要移除的文件路径

        Returns:
            是否成功移除
        """
        file_path = Path(target_file).resolve()
        if file_path in self._target_files:
            del self._target_files[file_path]
            del self._last_reload_map[file_path]
            logger.debug(f"[ConfigEventHandler] 移除文件监控: {file_path}")
            return True
        return False

    def get_monitored_files(self) -> list:
        """
        获取当前监控的文件列表

        Returns:
            监控的文件路径列表
        """
        return [str(p) for p in self._target_files.keys()]

    def on_modified(self, event):
        """
        文件修改事件处理

        Args:
            event: 文件系统事件
        """
        if event.is_directory:
            return

        event_path = Path(event.src_path).resolve()
        
        if event_path not in self._target_files:
            return

        current_time = time.time()
        last_reload = self._last_reload_map.get(event_path, 0)

        if current_time - last_reload < self._debounce_interval:
            return

        self._last_reload_map[event_path] = current_time
        callback = self._target_files[event_path]
        file_name = event_path.name

        logger.info(f"[ConfigWatcher] {file_name} 变更，热加载")

        try:
            callback(str(event_path))
            logger.info(f"[ConfigWatcher] {file_name} 热加载完成")
        except Exception as e:
            logger.error(f"[ConfigWatcher] {file_name} 热加载失败: {e}")

    def on_created(self, event):
        """文件创建事件处理"""
        self.on_modified(event)


class ConfigWatcher:
    """
    配置文件监控器

    支持同时监控多个文件变更，不依赖记忆系统。

    Attributes:
        _target_files: 目标文件路径到回调函数的映射
        _watch_dirs: 需要监控的目录集合
        observer: Watchdog 观察者实例
        _running: 是否正在运行
        _debounce_interval: 防抖间隔（秒）
        _handler: 事件处理器实例
    """

    def __init__(
        self,
        target_file: Optional[str] = None,
        reload_callback: Optional[Callable[[str], None]] = None,
        debounce_interval: float = 1.0
    ):
        """
        初始化配置文件监控器

        Args:
            target_file: 目标文件路径（可选，可通过 add_file 添加）
            reload_callback: 文件变更时的回调函数（可选）
            debounce_interval: 防抖间隔（秒），默认1秒

        Raises:
            ImportError: 如果 watchdog 库未安装
        """
        if not WATCHDOG_AVAILABLE:
            raise ImportError(
                "watchdog 库未安装，请运行: pip install watchdog"
            )

        self._target_files: Dict[Path, Callable[[str], None]] = {}
        self._watch_dirs: set = set()
        self.debounce_interval = debounce_interval

        self.observer = Observer()
        self._running = False
        self._handler: Optional[ConfigEventHandler] = None

        if target_file and reload_callback:
            self.add_file(target_file, reload_callback)

    def add_file(
        self,
        target_file: str,
        reload_callback: Callable[[str], None]
    ) -> bool:
        """
        添加要监控的文件

        Args:
            target_file: 目标文件路径
            reload_callback: 文件变更时的回调函数

        Returns:
            是否成功添加

        Raises:
            ValueError: 如果文件不存在
        """
        file_path = Path(target_file).resolve()

        if not file_path.exists():
            raise ValueError(f"文件不存在: {target_file}")

        if file_path in self._target_files:
            logger.warning(f"[ConfigWatcher] 文件已在监控中: {file_path}")
            return False

        self._target_files[file_path] = reload_callback
        self._watch_dirs.add(file_path.parent)

        if self._handler:
            self._handler.add_file(str(file_path), reload_callback)
            self._update_observer()

        logger.info(f"[ConfigWatcher] 添加文件监控: {file_path}")
        return True

    def remove_file(self, target_file: str) -> bool:
        """
        移除文件监控

        Args:
            target_file: 要移除的文件路径

        Returns:
            是否成功移除
        """
        file_path = Path(target_file).resolve()

        if file_path not in self._target_files:
            return False

        del self._target_files[file_path]

        if self._handler:
            self._handler.remove_file(str(file_path))

        logger.info(f"[ConfigWatcher] 移除文件监控: {file_path}")
        return True

    def get_monitored_files(self) -> list:
        """
        获取当前监控的文件列表

        Returns:
            监控的文件路径列表
        """
        return [str(p) for p in self._target_files.keys()]

    def _update_observer(self):
        """
        更新观察者监控的目录

        当添加新文件时，检查是否需要监控新的目录
        """
        if not self._running or not self._handler:
            return

        for watch_dir in self._watch_dirs:
            try:
                self.observer.schedule(
                    self._handler,
                    str(watch_dir),
                    recursive=False
                )
            except Exception:
                pass

    def start(self):
        """
        启动配置文件监控

        开始监控所有已注册的文件变更
        """
        if self._running:
            logger.warning("[ConfigWatcher] 监控器已经在运行中")
            return

        if not self._target_files:
            logger.warning("[ConfigWatcher] 没有注册任何文件，无法启动监控")
            return

        try:
            self._handler = ConfigEventHandler(
                debounce_interval=self.debounce_interval
            )

            for file_path, callback in self._target_files.items():
                self._handler.add_file(str(file_path), callback)

            for watch_dir in self._watch_dirs:
                self.observer.schedule(
                    self._handler,
                    str(watch_dir),
                    recursive=False
                )

            self.observer.start()
            self._running = True
            logger.info(f"[ConfigWatcher] 监控器已启动，监控 {len(self._target_files)} 个文件")

        except Exception as e:
            logger.error(f"[ConfigWatcher] 启动监控器失败: {e}")
            raise

    def stop(self):
        """
        停止配置文件监控

        停止监控并清理资源
        """
        if not self._running:
            return

        try:
            self.observer.stop()
            self.observer.join(timeout=5)
            self._running = False
            self._handler = None
            logger.info("[ConfigWatcher] 配置文件监控器已停止")
        except Exception as e:
            logger.error(f"[ConfigWatcher] 停止监控器失败: {e}")

    def is_running(self) -> bool:
        """
        检查监控器是否正在运行

        Returns:
            是否正在运行
        """
        return self._running


# 全局 ConfigWatcher 实例
_config_watcher_instance: Optional[ConfigWatcher] = None


def is_config_watcher_enabled() -> bool:
    """
    检查配置文件监控是否启用

    Returns:
        是否启用（默认 True）
    """
    from agent.config.configloader import GLOBAL_CONFIG
    hot_reload_config = GLOBAL_CONFIG.get("hot_reload", {})
    config_config = hot_reload_config.get("config", {})
    return config_config.get("enabled", True)


def get_config_watcher_config() -> dict:
    """
    获取配置文件监控配置

    Returns:
        配置字典
    """
    from agent.config.configloader import GLOBAL_CONFIG

    default_config = {
        "enabled": True,
        "debounce_interval": 1.0
    }

    hot_reload_config = GLOBAL_CONFIG.get("hot_reload", {})
    config_config = hot_reload_config.get("config", {})
    config = default_config.copy()
    config.update(config_config)

    return config


def start_config_watcher(
    target_file: Optional[str] = None,
    reload_callback: Optional[Callable[[str], None]] = None,
    agents_md_path: Optional[str] = None
) -> Optional[ConfigWatcher]:
    """
    启动配置文件监控器

    支持同时监控 config.json 和 agents.md 文件

    Args:
        target_file: 目标配置文件路径，默认监控 config.json
        reload_callback: 配置文件变更时的回调函数
        agents_md_path: agents.md 文件路径，默认监控 workspace/agents.md

    Returns:
        ConfigWatcher 实例，如果未启用或启动失败返回 None
    """
    global _config_watcher_instance

    if _config_watcher_instance is not None and _config_watcher_instance.is_running():
        logger.info("[ConfigWatcher] 监控器已在运行中")
        return _config_watcher_instance

    if not is_config_watcher_enabled():
        logger.info("[ConfigWatcher] 配置文件监控已禁用")
        return None

    config = get_config_watcher_config()
    debounce_interval = config.get("debounce_interval", 1.0)

    if target_file is None:
        from agent.config.configloader import GLOBAL_CONFIG
        if GLOBAL_CONFIG.current_config_path:
            target_file = GLOBAL_CONFIG.current_config_path
        else:
            target_file = os.path.join(GLOBAL_CONFIG.FICSBOT_DIR, "config.json")

    target_file = str(Path(target_file).resolve())

    try:
        _config_watcher_instance = ConfigWatcher(
            debounce_interval=debounce_interval
        )

        if reload_callback is None:
            reload_callback = _create_default_config_reload_callback()

        _config_watcher_instance.add_file(target_file, reload_callback)

        if agents_md_path is None:
            from agent.config.configloader import GLOBAL_CONFIG
            agents_md_path = os.path.join(GLOBAL_CONFIG.FICSBOT_DIR, "workspace", "agents.md")

        agents_md_path = str(Path(agents_md_path).resolve())

        if Path(agents_md_path).exists():
            agents_md_callback = _create_agents_md_reload_callback()
            _config_watcher_instance.add_file(agents_md_path, agents_md_callback)
            logger.info(f"[ConfigWatcher] 添加 agents.md 监控: {agents_md_path}")

        _config_watcher_instance.start()

        return _config_watcher_instance

    except ImportError as e:
        logger.warning(f"[ConfigWatcher] watchdog 库未安装: {e}")
        return None
    except Exception as e:
        logger.error(f"[ConfigWatcher] 启动失败: {e}")
        _config_watcher_instance = None
        return None


def _create_default_config_reload_callback() -> Callable[[str], None]:
    """
    创建默认的配置文件重载回调函数

    Returns:
        回调函数
    """
    def default_reload_callback(file_path: str):
        """默认回调：重新加载全局配置并更新所有 Agent（轻量级）"""
        logger.info(f"[ConfigWatcher] 重新加载配置: {file_path}")
        try:
            from agent.config.configloader import GLOBAL_CONFIG
            from agent.registry import AGENT_REGISTRY
            
            GLOBAL_CONFIG.reload()
            logger.info("[ConfigWatcher] 全局配置重载完成")
            
            AGENT_REGISTRY._load_configs()
            logger.info("[ConfigWatcher] AgentRegistry 配置重载完成")
            
            reloaded_agents = []
            for agent_id in list(AGENT_REGISTRY._agents.keys()):
                agent = AGENT_REGISTRY._agents.get(agent_id)
                if agent is None:
                    continue
                try:
                    agent.reload_config_only()
                    reloaded_agents.append(agent_id)
                    if hasattr(agent, 'llm_client') and agent.llm_client:
                        current_model = agent.llm_client.current_model_alias
                        logger.info(f"[ConfigWatcher] Agent '{agent_id}' 配置已更新，当前模型: {current_model}")
                except Exception as e:
                    logger.error(f"[ConfigWatcher] Agent '{agent_id}' 配置更新失败: {e}")
            
            if reloaded_agents:
                logger.info(f"[ConfigWatcher] 共更新 {len(reloaded_agents)} 个 Agent 配置: {reloaded_agents}")
            else:
                logger.info("[ConfigWatcher] 暂无已创建的 Agent 实例，配置将在下次创建 Agent 时生效")
                
        except Exception as e:
            logger.error(f"[ConfigWatcher] 配置重载失败: {e}")

    return default_reload_callback


def _create_agents_md_reload_callback() -> Callable[[str], None]:
    """
    创建 agents.md 文件重载回调函数

    Returns:
        回调函数
    """
    def agents_md_reload_callback(file_path: str):
        """agents.md 回调：重新加载 Agent 配置模板"""
        logger.info(f"[ConfigWatcher] agents.md 变更，重新加载: {file_path}")
        try:
            from agent.registry import AGENT_REGISTRY
            
            AGENT_REGISTRY._load_configs()
            logger.info("[ConfigWatcher] Agent 配置模板重载完成")
            
            reloaded_agents = []
            for agent_id in list(AGENT_REGISTRY._agents.keys()):
                agent = AGENT_REGISTRY._agents.get(agent_id)
                if agent is None:
                    continue
                try:
                    agent.reload_config_only()
                    reloaded_agents.append(agent_id)
                except Exception as e:
                    logger.error(f"[ConfigWatcher] Agent '{agent_id}' 配置更新失败: {e}")
            
            if reloaded_agents:
                logger.info(f"[ConfigWatcher] 共更新 {len(reloaded_agents)} 个 Agent 配置: {reloaded_agents}")
                
        except Exception as e:
            logger.error(f"[ConfigWatcher] agents.md 重载失败: {e}")

    return agents_md_reload_callback


def add_watched_file(
    target_file: str,
    reload_callback: Callable[[str], None]
) -> bool:
    """
    向运行中的监控器添加文件

    Args:
        target_file: 要监控的文件路径
        reload_callback: 文件变更时的回调函数

    Returns:
        是否成功添加
    """
    global _config_watcher_instance

    if _config_watcher_instance is None:
        logger.warning("[ConfigWatcher] 监控器未启动，无法添加文件")
        return False

    try:
        return _config_watcher_instance.add_file(target_file, reload_callback)
    except Exception as e:
        logger.error(f"[ConfigWatcher] 添加文件监控失败: {e}")
        return False


def remove_watched_file(target_file: str) -> bool:
    """
    从运行中的监控器移除文件

    Args:
        target_file: 要移除的文件路径

    Returns:
        是否成功移除
    """
    global _config_watcher_instance

    if _config_watcher_instance is None:
        return False

    try:
        return _config_watcher_instance.remove_file(target_file)
    except Exception as e:
        logger.error(f"[ConfigWatcher] 移除文件监控失败: {e}")
        return False


def stop_config_watcher() -> bool:
    """
    停止配置文件监控器

    Returns:
        是否成功停止
    """
    global _config_watcher_instance

    if _config_watcher_instance is None:
        return True

    try:
        _config_watcher_instance.stop()
        _config_watcher_instance = None
        logger.info("[ConfigWatcher] 配置文件监控器已停止")
        return True
    except Exception as e:
        logger.error(f"[ConfigWatcher] 停止失败: {e}")
        return False


def get_config_watcher() -> Optional[ConfigWatcher]:
    """
    获取当前的 ConfigWatcher 实例

    Returns:
        ConfigWatcher 实例，如果未启动返回 None
    """
    return _config_watcher_instance


def is_config_watcher_running() -> bool:
    """
    检查配置文件监控器是否正在运行

    Returns:
        是否正在运行
    """
    if _config_watcher_instance is None:
        return False

    try:
        return _config_watcher_instance.is_running()
    except Exception:
        return False
