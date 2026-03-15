#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :agent_initializer.py
# @Time      :2026/03/10
# @Author    :Ficus

"""
Agent 初始化器模块

该模块负责初始化 Agent 的各种扩展模块:
    - MCP (Model Context Protocol)
    - 浏览器工具
    - 记忆系统
    - 任务拆解模块
"""

from typing import TYPE_CHECKING

from colorama import Fore, Style
from loguru import logger

from agent.config.configloader import GLOBAL_CONFIG

if TYPE_CHECKING:
    from agent.core.agent import Agent


class AgentInitializer:
    """
    Agent 初始化器，负责初始化各种扩展模块
    
    功能说明:
        - 初始化 MCP 模块
        - 初始化浏览器工具
        - 初始化记忆系统
        - 初始化任务拆解模块
    
    核心方法:
        - init_mcp: 初始化 MCP 模块
        - init_browser: 初始化浏览器工具
        - init_memory: 初始化记忆系统
        - init_task_decomposition: 初始化任务拆解模块
    """
    
    @staticmethod
    def init_mcp(agent: "Agent") -> None:
        """
        初始化 MCP (Model Context Protocol) 模块
        
        功能说明:
            - 检查是否启用 MCP 功能
            - 创建 MCPManager 并加载服务器配置
            - 连接所有启用的 MCP Server
            - 将 MCP 工具注册到 ToolAdapter
        
        配置项:
            - enable_mcp: 是否启用 MCP 功能，默认 True
        
        Args:
            agent: Agent 实例
        """
        enable_mcp = GLOBAL_CONFIG.get("enable_mcp", True)
        
        if not enable_mcp:
            logger.info(f"{Fore.CYAN}[MCP] MCP 功能已禁用{Style.RESET_ALL}")
            agent.mcp_manager = None
            agent.mcp_tool_adapter = None
            return
        
        try:
            from agent.mcp import MCPManager, MCPToolAdapter
            
            agent.mcp_manager = MCPManager()
            server_count = agent.mcp_manager.load_servers()
            
            if server_count > 0:
                results = agent.mcp_manager.connect_all_sync()
                connected_count = sum(1 for v in results.values() if v)
                logger.info(f"{Fore.CYAN}[MCP] 已连接 {connected_count}/{server_count} 个 MCP 服务器{Style.RESET_ALL}")
                
                agent.mcp_tool_adapter = MCPToolAdapter(agent.mcp_manager)
                registered_count = agent.mcp_tool_adapter.register_to_tool_adapter(agent.tool_adapter)
                logger.info(f"{Fore.CYAN}[MCP] 已注册 {registered_count} 个 MCP 工具{Style.RESET_ALL}")
            else:
                logger.info(f"{Fore.CYAN}[MCP] 未配置任何 MCP 服务器{Style.RESET_ALL}")
                agent.mcp_tool_adapter = None
                
        except ImportError as e:
            logger.warning(f"{Fore.YELLOW}[MCP] MCP SDK 未安装，跳过 MCP 初始化: {e}{Style.RESET_ALL}")
            logger.warning(f"{Fore.YELLOW}[MCP] 请运行: pip install mcp{Style.RESET_ALL}")
            agent.mcp_manager = None
            agent.mcp_tool_adapter = None
        except Exception as e:
            logger.error(f"{Fore.RED}[MCP] MCP 初始化失败: {e}{Style.RESET_ALL}")
            agent.mcp_manager = None
            agent.mcp_tool_adapter = None
    
    @staticmethod
    def init_browser(agent: "Agent") -> None:
        """
        初始化浏览器工具模块
        
        功能说明:
            - 检查是否启用浏览器功能
            - 创建 BrowserTool 实例
            - 将浏览器工具注册到 ToolAdapter
        
        Args:
            agent: Agent 实例
        """
        enable_browser = GLOBAL_CONFIG.get("enable_browser", True)
        
        if not enable_browser:
            logger.info(f"{Fore.CYAN}[Browser] 浏览器功能已禁用{Style.RESET_ALL}")
            agent.browser_tool = None
            return
        
        try:
            from agent.tool.browsertool import BrowserTool
            agent.browser_tool = BrowserTool.get_instance()
            agent.tool_adapter.browser_tool = agent.browser_tool
            registered_count = agent.browser_tool.register_to_tool_adapter(agent.tool_adapter)
            logger.info(f"{Fore.CYAN}[Browser] Registered {registered_count} browser tools{Style.RESET_ALL}")
            
        except ImportError as e:
            logger.warning(f"{Fore.YELLOW}[Browser] browser-use 未安装: {e}{Style.RESET_ALL}")
            logger.warning(f"{Fore.YELLOW}[Browser] 请运行: pip install browser-use playwright && playwright install chromium{Style.RESET_ALL}")
            agent.browser_tool = None
        except Exception as e:
            logger.error(f"{Fore.RED}[Browser] 浏览器工具初始化失败: {e}{Style.RESET_ALL}")
            agent.browser_tool = None

    @staticmethod
    def init_memory(agent: "Agent") -> None:
        """
        初始化记忆系统模块
        
        功能说明:
            - 检查是否启用记忆系统功能
            - 创建 MemorySystem 实例
            - 将记忆系统工具注册到 ToolAdapter
            - 处理工具索引并同步到数据库
            - 从内存中移除已加入记忆索引的工具
        
        配置项:
            - memory.enabled: 是否启用记忆系统
            - memory.db_path: 向量数据库路径
            - memory.index_path: 索引文件路径
        
        Args:
            agent: Agent 实例
        """
        memory_config = GLOBAL_CONFIG.get("memory", {})
        enabled = memory_config.get("enabled", False)
        
        if not enabled:
            logger.info(f"{Fore.CYAN}[Memory] 记忆系统已禁用{Style.RESET_ALL}")
            agent.memory_system = None
            AgentInitializer._update_injected_skill_list(agent, set())
            return
        
        try:
            from agent.memory import MemorySystem
            agent.memory_system = MemorySystem(memory_config)
            agent.tool_adapter.memory_system = agent.memory_system
            
            config = agent.tool_adapter._load_tools_config()
            for tool_def in config.get("memory_tools", []):
                tool_name = tool_def["name"]
                tool_def["func"] = agent.tool_adapter._get_memory_tool_func(tool_name)
                agent.tool_adapter.tools[tool_name] = tool_def
            
            logger.info(f"{Fore.CYAN}[Memory] 记忆系统工具注册完成，共 {len(config.get('memory_tools', []))} 个{Style.RESET_ALL}")
            
            all_tools = agent.tool_adapter.list_tools()
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(agent.memory_system.init_async(all_tools))
                
                memory_tool_names = AgentInitializer._process_memory_init_result(agent, result)
                
                AgentInitializer._update_injected_skill_list(agent, memory_tool_names)
                
                loop.close()
            except RuntimeError:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        AgentInitializer._run_memory_init_async, 
                        agent, 
                        all_tools
                    )
                    future.result()
            
            # 启动 MD 文件监控器（监控 MD 文件变更）
            AgentInitializer._start_file_watcher(agent)

        except ImportError as e:
            logger.warning(f"{Fore.YELLOW}[Memory] 记忆系统依赖未安装: {e}{Style.RESET_ALL}")
            agent.memory_system = None
            AgentInitializer._update_injected_skill_list(agent, set())
        except Exception as e:
            logger.error(f"{Fore.RED}[Memory] 记忆系统初始化失败: {e}{Style.RESET_ALL}")
            agent.memory_system = None
            AgentInitializer._update_injected_skill_list(agent, set())

    @staticmethod
    def _run_memory_init_async(agent: "Agent", all_tools: list) -> None:
        """在独立线程中运行异步初始化"""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(agent.memory_system.init_async(all_tools))
        
        memory_tool_names = AgentInitializer._process_memory_init_result(agent, result)
        AgentInitializer._update_injected_skill_list(agent, memory_tool_names)
        
        loop.close()

    @staticmethod
    def _process_memory_init_result(agent: "Agent", result: dict) -> set:
        """
        处理记忆系统初始化结果
        
        Args:
            agent: Agent 实例
            result: 初始化结果字典
        
        Returns:
            记忆工具名称集合
        """
        memory_tool_names = set()
        for tool in result.get("memory_tools", []):
            func_def = tool.get("function", tool)
            name = func_def.get("name")
            if name:
                memory_tool_names.add(name)
        
        removed_tools = []
        for name in memory_tool_names:
            if name in agent.tool_adapter.tools:
                del agent.tool_adapter.tools[name]
                removed_tools.append(name)
        
        if removed_tools:
            logger.debug(f"从内存移除工具（已加入记忆索引）: {removed_tools}")
        
        if memory_tool_names:
            resident_tools = list(agent.tool_adapter.tools.keys())
            logger.info(f"{Fore.CYAN}[Memory] 已将 {len(memory_tool_names)} 个工具移入记忆索引，当前常驻工具 {len(resident_tools)} 个: {resident_tools}{Style.RESET_ALL}")
        
        return memory_tool_names

    @staticmethod
    def _update_injected_skill_list(agent: "Agent", memory_tool_names: set) -> None:
        """
        注入常驻工具列表和过滤后的技能列表到 system prompt
        
        Args:
            agent: Agent 实例
            memory_tool_names: 已加入记忆索引的工具名称集合
        """
        try:
            AgentInitializer._inject_tool_list(agent)
            AgentInitializer._inject_skill_list_filtered(agent, memory_tool_names)
        except Exception as e:
            logger.warning(f"{Fore.YELLOW}[Memory] 注入列表失败: {e}{Style.RESET_ALL}")

    @staticmethod
    def _inject_tool_list(agent: "Agent") -> None:
        """
        注入常驻工具列表到 {INJECTED_TOOL_LIST} 占位符
        
        Args:
            agent: Agent 实例
        """
        try:
            resident_tools = list(agent.tool_adapter.tools.keys())
            lines = []
            for name in sorted(resident_tools):
                if name in agent.tool_adapter.tools:
                    info = agent.tool_adapter.tools[name]
                    desc = info.get("description", "")[:60]
                    lines.append(f"- **{name}**: {desc}")
            
            tool_list_str = "\n".join(lines) if lines else "_暂无常驻工具_"
            agent.conversation.inject_tool_list(tool_list_str)
            logger.info(f"{Fore.CYAN}[工具列表注入] 成功注入 {len(resident_tools)} 个常驻工具{Style.RESET_ALL}")
        except Exception as e:
            logger.warning(f"{Fore.YELLOW}[工具列表注入] 失败: {e}{Style.RESET_ALL}")

    @staticmethod
    def _inject_skill_list_filtered(agent: "Agent", memory_tool_names: set) -> None:
        """
        注入技能列表到 {INJECTED_SKILLS_LIST} 占位符
        
        根据 tool_index.json 中的 add_to_memory 配置过滤技能：
        - add_to_memory=true 的技能不在常驻列表显示，需通过 discover 发现
        - add_to_memory=false 或未配置的技能在常驻列表显示
        
        技能列表包含: name, description, filepath
        
        Args:
            agent: Agent 实例
            memory_tool_names: 已加入记忆索引的工具名称集合（保留参数兼容性）
        """
        try:
            import json5
            from pathlib import Path
            
            memory_index_path = Path(agent.skill_loader.skill_root_dir).parent / "memory" / "memory_index"
            tool_index_file = memory_index_path / "tool_index.json"
            
            memory_skills = set()
            if tool_index_file.exists():
                with open(tool_index_file, "r", encoding="utf-8") as f:
                    index_data = json5.load(f)
                for tool in index_data.get("tools", []):
                    if tool.get("tool_type") == "skill" and tool.get("add_to_memory", False):
                        tool_name = tool.get("name", "")
                        if tool_name.startswith("skill_"):
                            memory_skills.add(tool_name[6:])
            
            unique_skills = {skill["name"]: skill for skill in agent.skill_loader.skills.values()}
            
            lines = []
            filtered_count = 0
            for skill_name, skill_info in unique_skills.items():
                if skill_name in memory_skills:
                    filtered_count += 1
                    continue
                desc = skill_info.get("description", "")[:80]
                filepath = skill_info.get("skill_md_path", "")
                lines.append(f"- name: {skill_name}\n  description: {desc}\n  filepath: {filepath}")
            
            skill_list_str = "\n".join(lines) if lines else "_暂无可用技能_"
            agent.conversation.inject_skill_list(skill_list_str)
            logger.info(f"{Fore.CYAN}[技能列表注入] 成功注入 {len(lines)} 个技能，已过滤 {filtered_count} 个记忆索引技能{Style.RESET_ALL}")
        except Exception as e:
            logger.warning(f"{Fore.YELLOW}[技能列表注入] 失败: {e}{Style.RESET_ALL}")

    @staticmethod
    def _start_file_watcher(agent: "Agent") -> None:
        """
        启动 MD 文件监控器

        监控 MD 记忆文件变更，用户编辑自动同步到向量库。
        根据 config.file_watcher.enabled 配置决定是否启动（默认启用）。
        支持多 Agent 架构，每个 Agent 独立管理监控器。

        Args:
            agent: Agent 实例
        """
        if agent.memory_system is None:
            return

        try:
            from agent.watchdog.file_watcher_start import start_file_watcher

            # 启动 MD 文件监控器（传递 agent_id 支持多 Agent）
            watcher = start_file_watcher(
                memory_system=agent.memory_system,
                agent_id=agent.agent_id
            )

            if watcher:
                logger.info(f"{Fore.CYAN}[FileWatcher] Agent '{agent.agent_id}' MD 文件监控器启动成功{Style.RESET_ALL}")
            else:
                logger.info(f"{Fore.YELLOW}[FileWatcher] Agent '{agent.agent_id}' MD 文件监控器未启动（可能已禁用）{Style.RESET_ALL}")

        except ImportError as e:
            logger.warning(f"{Fore.YELLOW}[FileWatcher] 文件监控模块未安装: {e}{Style.RESET_ALL}")
            logger.warning(f"{Fore.YELLOW}[FileWatcher] 请运行: pip install watchdog{Style.RESET_ALL}")
        except Exception as e:
            logger.error(f"{Fore.RED}[FileWatcher] Agent '{agent.agent_id}' 启动 MD 文件监控器失败: {e}{Style.RESET_ALL}")

    @staticmethod
    def _start_config_watcher(agent: "Agent") -> None:
        """
        启动配置文件监控器

        监控配置文件变更并自动热加载。
        根据 hot_reload.config.enabled 配置决定是否启动（默认启用）。
        独立于记忆系统，即使记忆功能禁用也会启动。

        热加载时会自动重载所有已创建的 Agent 实例（通过 AgentRegistry）。

        Args:
            agent: Agent 实例（用于日志记录，实际重载通过 AgentRegistry 管理）
        """
        try:
            from agent.watchdog.config_watcher import start_config_watcher

            watcher = start_config_watcher()

            if watcher:
                logger.info(f"{Fore.CYAN}[ConfigWatcher] 配置文件监控器启动成功{Style.RESET_ALL}")
            else:
                logger.info(f"{Fore.YELLOW}[ConfigWatcher] 配置文件监控器未启动（可能已禁用）{Style.RESET_ALL}")

        except ImportError as e:
            logger.warning(f"{Fore.YELLOW}[ConfigWatcher] 文件监控模块未安装: {e}{Style.RESET_ALL}")
            logger.warning(f"{Fore.YELLOW}[ConfigWatcher] 请运行: pip install watchdog{Style.RESET_ALL}")
        except Exception as e:
            logger.error(f"{Fore.RED}[ConfigWatcher] 启动配置文件监控器失败: {e}{Style.RESET_ALL}")

    @staticmethod
    def _start_tool_index_watcher(agent: "Agent") -> None:
        """
        启动工具索引文件监控器

        监控 tool_index.json 变更并自动热加载。
        根据 hot_reload.tool_index.enabled 配置决定是否启动（默认启用）。
        独立于记忆系统，即使记忆功能禁用也会启动。

        Args:
            agent: Agent 实例
        """
        try:
            from agent.watchdog.tool_index_watcher import (
                start_tool_index_watcher,
                set_agent_instance
            )

            set_agent_instance(agent)

            watcher = start_tool_index_watcher()

            if watcher:
                logger.info(f"{Fore.CYAN}[ToolIndexWatcher] 工具索引监控器启动成功{Style.RESET_ALL}")
            else:
                logger.info(f"{Fore.YELLOW}[ToolIndexWatcher] 工具索引监控器未启动（可能已禁用）{Style.RESET_ALL}")

        except ImportError as e:
            logger.warning(f"{Fore.YELLOW}[ToolIndexWatcher] 文件监控模块未安装: {e}{Style.RESET_ALL}")
            logger.warning(f"{Fore.YELLOW}[ToolIndexWatcher] 请运行: pip install watchdog{Style.RESET_ALL}")
        except Exception as e:
            logger.error(f"{Fore.RED}[ToolIndexWatcher] 启动工具索引监控器失败: {e}{Style.RESET_ALL}")

    @staticmethod
    def init_task_decomposition(agent: "Agent") -> None:
        """
        初始化任务拆解模块
        
        功能说明:
            - 创建 TaskDecomposer、TaskTreeManager、HeartbeatManager 实例
            - 支持任务拆解、任务树持久化、心跳状态管理
            - 支持断点续跑
        
        配置项:
            - workspace_root: 工作区根目录
        
        Args:
            agent: Agent 实例
        """
        try:
            from agent.core.task.task_decomposer import TaskDecomposer
            from agent.core.task.task_tree_manager import TaskTreeManager
            from agent.core.task.heartbeat_manager import HeartbeatManager
            
            workspace_root = GLOBAL_CONFIG.get("workspace_root", "./workspace")
            
            agent.task_decomposer = TaskDecomposer(agent.llm_client, workspace_root)
            agent.task_tree_manager = TaskTreeManager(workspace_root)
            agent.heartbeat_manager = HeartbeatManager(workspace_root)
            
            logger.info(f"{Fore.CYAN}[任务拆解] 模块初始化完成{Style.RESET_ALL}")
            
        except Exception as e:
            logger.error(f"{Fore.RED}[任务拆解] 模块初始化失败: {e}{Style.RESET_ALL}")
            agent.task_decomposer = None
            agent.task_tree_manager = None
            agent.heartbeat_manager = None
