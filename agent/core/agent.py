#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :agent.py
# @Time      :2026/03/07
# @Author    :Ficus

"""
核心 Agent 调度器模块

该模块定义了核心 Agent 类，负责协调对话、工具调用和技能执行。
"""
import json
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

from colorama import Fore, Style
from loguru import logger

from agent.config.configloader import GLOBAL_CONFIG
from agent.core.conversation import ConversationManager
from agent.fileSystem.filesystem import FileSystemTool
from agent.provider.llmclient import LLMClient
from agent.skill.skill_loader import SkillLoader
from agent.memory import MemorySystem
from agent.tool.browsertool import BrowserTool
from agent.tool.shelltool import ShellTool
from agent.tool.tooladapter import ToolAdapter

if TYPE_CHECKING:
    from agent.config.agent_config import AgentConfig


def print_conversation_history(messages: list, max_content_length: int = 100, print_last_only: bool = False):
    """
    打印对话历史信息（全局工具函数）。

    功能说明:
        - 格式化打印对话消息列表
        - 支持不同角色的颜色区分
        - 支持只打印最后一条消息

    参数:
        messages: 对话消息列表
        max_content_length: 内容最大显示长度，默认100字符
        print_last_only: 是否只打印最后一条消息，默认False打印全部

    颜色说明:
        - system: 紫色
        - user: 黄色
        - assistant: 绿色
        - tool: 蓝色
        - 其他: 白色
    """
    messages_to_print = [messages[-1]] if print_last_only and messages else messages

    for msg in messages_to_print:
        idx = messages.index(msg) if msg in messages else 0
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')
        tool_calls = msg.get('tool_calls', None)
        tool_call_id = msg.get('tool_call_id', None)
        if role == 'system':
            logger.debug(f"{Fore.MAGENTA}[历史 {idx}] system: {content[:max_content_length]}{Style.RESET_ALL}")
        elif role == 'user':
            logger.debug(f"{Fore.YELLOW}[历史 {idx}] user: {content[:max_content_length]}{Style.RESET_ALL}")
        elif role == 'assistant':
            if tool_calls:
                tool_names = [tc.get('function', {}).get('name', 'unknown') for tc in tool_calls]
                logger.debug(f"{Fore.GREEN}[历史 {idx}] assistant(tool): {tool_names}{Style.RESET_ALL}")
            else:
                logger.debug(f"{Fore.GREEN}[历史 {idx}] assistant: {content[:max_content_length]}{Style.RESET_ALL}")
        elif role == 'tool':
            logger.debug(f"{Fore.BLUE}[历史 {idx}] tool({tool_call_id}): {content[:max_content_length]}{Style.RESET_ALL}")
        else:
            logger.debug(f"{Fore.WHITE}[历史 {idx}] {role}: {content[:max_content_length]}{Style.RESET_ALL}")


class Agent:
    """
    核心Agent调度器，负责协调对话、工具调用和技能执行。
    
    功能说明:
        - 管理对话上下文和历史记录
        - 处理用户输入并调用大模型
        - 支持工具调用（文件操作、Shell命令、技能等）
        - 支持流式和非流式响应
        - 支持技能自动检测和调用
        - 支持多Agent架构和子代理委托
    
    核心方法:
        - chat: 非流式对话（用于CLI和API）
        - chat_stream: 流式对话（用于旧API兼容）
        - reload: 重载所有组件配置
    
    技能调用流程:
        1. 用户输入 → _detect_skill_from_input 检测技能
        2. 准备工具清单 → _prepare_tools_for_skill 优先显示检测到的技能
        3. 大模型选择 skill_xxx → ToolAdapter.call_tool 调用
        4. SkillLoader.execute 返回技能说明（非直接执行）
        5. 大模型根据说明选择具体工具 → 多轮工具调用 → 完成
    
    配置项:
        - max_tool_calls: 最大工具调用次数，默认10次
        - agent_config: Agent配置对象，支持多Agent架构
        - delegation_depth: 当前委托深度，用于子代理调用
    """
    
    def __init__(
        self, 
        session_id: Optional[str] = None, 
        enable_persistence: bool = True,
        agent_config: Optional["AgentConfig"] = None,
        delegation_depth: int = 0
    ):
        """
        初始化 Agent。

        参数:
            session_id: 会话ID，为None时自动创建新会话
            enable_persistence: 是否启用会话持久化，默认True
            agent_config: Agent配置对象，为None时使用默认配置
            delegation_depth: 当前委托深度，用于子代理调用时防止无限递归
        """
        self.agent_config = agent_config
        self.delegation_depth = delegation_depth
        self.agent_id = agent_config.agent_id if agent_config else "default"
        
        self.file_tool = FileSystemTool(agent_config)
        self.shell_tool = ShellTool(agent_config)
        self.skill_loader = SkillLoader()
        self.tool_adapter = ToolAdapter(
            self.file_tool, 
            self.shell_tool, 
            self.skill_loader,
            delegation_depth=delegation_depth
        )
        self.conversation = ConversationManager(session_id, enable_persistence)
        
        if agent_config and agent_config.system_prompt:
            self.conversation.custom_system_prompt = agent_config.system_prompt
        
        skill_patterns = agent_config.skills if agent_config else None
        skill_list_str = self.skill_loader.get_skill_list_info(skill_patterns)
        self.conversation.inject_skill_list(skill_list_str)
        
        if agent_config and agent_config.model:
            self.llm_client = LLMClient(default_model=agent_config.model)
            if agent_config.llm_preset:
                llm_params = agent_config.get_llm_params()
                self.llm_client.apply_preset(llm_params)
        else:
            self.llm_client = LLMClient()
        
        if agent_config and agent_config.max_tool_calls:
            self.max_tool_calls = agent_config.max_tool_calls
        else:
            self.max_tool_calls = GLOBAL_CONFIG.get("llm", {}).get("max_tool_calls", 10)
        
        self._last_skill_call: Optional[str] = None
        self._last_skill_repeat_count: int = 0
        self._max_skill_repeats = 1
        self._blocked_skills: set = set()
        self._auto_save = GLOBAL_CONFIG.get("session.auto_save", True)
        logger.info(f"{Fore.CYAN}初始化 Agent: {self.agent_id}, 最大工具调用次数: {self.max_tool_calls}{Style.RESET_ALL}")
        
        self._init_mcp()
        self._init_browser()
        self._init_memory()

    def _init_mcp(self):
        """
        初始化 MCP (Model Context Protocol) 模块。
        
        功能说明:
            - 检查是否启用 MCP 功能
            - 创建 MCPManager 并加载服务器配置
            - 连接所有启用的 MCP Server
            - 将 MCP 工具注册到 ToolAdapter
        
        配置项:
            - enable_mcp: 是否启用 MCP 功能，默认 True
        """
        enable_mcp = GLOBAL_CONFIG.get("enable_mcp", True)
        
        if not enable_mcp:
            logger.info(f"{Fore.CYAN}[MCP] MCP 功能已禁用{Style.RESET_ALL}")
            self.mcp_manager = None
            self.mcp_tool_adapter = None
            return
        
        try:
            from agent.mcp import MCPManager, MCPToolAdapter
            
            self.mcp_manager = MCPManager()
            server_count = self.mcp_manager.load_servers()
            
            if server_count > 0:
                results = self.mcp_manager.connect_all_sync()
                connected_count = sum(1 for v in results.values() if v)
                logger.info(f"{Fore.CYAN}[MCP] 已连接 {connected_count}/{server_count} 个 MCP 服务器{Style.RESET_ALL}")
                
                self.mcp_tool_adapter = MCPToolAdapter(self.mcp_manager)
                registered_count = self.mcp_tool_adapter.register_to_tool_adapter(self.tool_adapter)
                logger.info(f"{Fore.CYAN}[MCP] 已注册 {registered_count} 个 MCP 工具{Style.RESET_ALL}")
            else:
                logger.info(f"{Fore.CYAN}[MCP] 未配置任何 MCP 服务器{Style.RESET_ALL}")
                self.mcp_tool_adapter = None
                
        except ImportError as e:
            logger.warning(f"{Fore.YELLOW}[MCP] MCP SDK 未安装，跳过 MCP 初始化: {e}{Style.RESET_ALL}")
            logger.warning(f"{Fore.YELLOW}[MCP] 请运行: pip install mcp{Style.RESET_ALL}")
            self.mcp_manager = None
            self.mcp_tool_adapter = None
        except Exception as e:
            logger.error(f"{Fore.RED}[MCP] MCP 初始化失败: {e}{Style.RESET_ALL}")
            self.mcp_manager = None
            self.mcp_tool_adapter = None
    
    def _init_browser(self):
        """
        初始化浏览器工具模块（参考 _init_mcp 实现）
        
        功能说明:
            - 检查是否启用浏览器功能
            - 创建 BrowserTool 实例
            - 将浏览器工具注册到 ToolAdapter
        """
        enable_browser = GLOBAL_CONFIG.get("enable_browser", True)
        
        if not enable_browser:
            logger.info(f"{Fore.CYAN}[Browser] 浏览器功能已禁用{Style.RESET_ALL}")
            self.browser_tool = None
            return
        
        try:
            self.browser_tool = BrowserTool.get_instance()
            registered_count = self.browser_tool.register_to_tool_adapter(self.tool_adapter)
            logger.info(f"{Fore.CYAN}[Browser] Registered {registered_count} browser tools{Style.RESET_ALL}")
            
        except ImportError as e:
            logger.warning(f"{Fore.YELLOW}[Browser] browser-use 未安装: {e}{Style.RESET_ALL}")
            logger.warning(f"{Fore.YELLOW}[Browser] 请运行: pip install browser-use playwright && playwright install chromium{Style.RESET_ALL}")
            self.browser_tool = None
        except Exception as e:
            logger.error(f"{Fore.RED}[Browser] 浏览器工具初始化失败: {e}{Style.RESET_ALL}")
            self.browser_tool = None

    def _init_memory(self):
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
        """
        memory_config = GLOBAL_CONFIG.get("memory", {})
        enabled = memory_config.get("enabled", False)
        
        if not enabled:
            logger.info(f"{Fore.CYAN}[Memory] 记忆系统已禁用{Style.RESET_ALL}")
            self.memory_system = None
            return
        
        try:
            self.memory_system = MemorySystem(memory_config)
            self.tool_adapter.memory_system = self.memory_system
            
            config = self.tool_adapter._load_tools_config()
            for tool_def in config.get("memory_tools", []):
                tool_name = tool_def["name"]
                tool_def["func"] = self.tool_adapter._get_memory_tool_func(tool_name)
                self.tool_adapter.tools[tool_name] = tool_def
            
            logger.info(f"{Fore.CYAN}[Memory] 记忆系统工具注册完成，共 {len(config.get('memory_tools', []))} 个{Style.RESET_ALL}")
            
            all_tools = self.tool_adapter.list_tools()
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(self.memory_system.init_async(all_tools))
                
                memory_tool_names = set()
                for tool in result.get("memory_tools", []):
                    func_def = tool.get("function", tool)
                    name = func_def.get("name")
                    if name:
                        memory_tool_names.add(name)
                
                for name in memory_tool_names:
                    if name in self.tool_adapter.tools:
                        del self.tool_adapter.tools[name]
                        logger.debug(f"  - 从内存移除工具（已加入记忆索引）: {name}")
                
                if memory_tool_names:
                    logger.info(f"{Fore.CYAN}[Memory] 已将 {len(memory_tool_names)} 个工具移入记忆索引，当前常驻工具 {len(self.tool_adapter.tools)} 个{Style.RESET_ALL}")
                    
                    self._update_injected_skill_list(memory_tool_names)
                
                loop.close()
            except RuntimeError:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(self._run_memory_init_async, all_tools)
                    future.result()
            
        except ImportError as e:
            logger.warning(f"{Fore.YELLOW}[Memory] 记忆系统依赖未安装: {e}{Style.RESET_ALL}")
            self.memory_system = None
        except Exception as e:
            logger.error(f"{Fore.RED}[Memory] 记忆系统初始化失败: {e}{Style.RESET_ALL}")
            self.memory_system = None

    def _run_memory_init_async(self, all_tools):
        """在独立线程中运行异步初始化"""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.memory_system.init_async(all_tools))
        loop.close()

    def _update_injected_skill_list(self, memory_tool_names: set):
        """
        更新注入的技能列表，移除已加入记忆索引的技能
        
        Args:
            memory_tool_names: 已加入记忆索引的工具名称集合
        """
        try:
            current_prompt = self.conversation.system_prompt
            lines_to_remove = []
            
            for tool_name in memory_tool_names:
                if tool_name.startswith("skill_"):
                    skill_name = tool_name[6:]
                    lines_to_remove.append(f"- name: {skill_name}")
            
            if not lines_to_remove:
                return
            
            lines = current_prompt.split('\n')
            new_lines = []
            skip_next = False
            
            for i, line in enumerate(lines):
                if skip_next:
                    skip_next = False
                    continue
                    
                should_remove = False
                for remove_prefix in lines_to_remove:
                    if line.strip().startswith(remove_prefix):
                        should_remove = True
                        break
                
                if should_remove:
                    if i + 1 < len(lines) and lines[i + 1].strip().startswith("description:"):
                        skip_next = True
                    continue
                    
                new_lines.append(line)
            
            self.conversation._base_system_prompt = '\n'.join(new_lines)
            self.conversation.system_prompt = self.conversation._base_system_prompt
            
            logger.info(f"{Fore.CYAN}[Memory] 已从 system prompt 移除 {len(lines_to_remove)} 个记忆索引技能{Style.RESET_ALL}")
            
        except Exception as e:
            logger.warning(f"{Fore.YELLOW}[Memory] 更新技能列表失败: {e}{Style.RESET_ALL}")

    def reload(self):
        """
        重载所有组件配置。
        
        功能说明:
            - 重载全局配置
            - 重新加载 Agent 配置（如果使用 agent_config）
            - 重新初始化所有工具（文件、Shell、技能）
            - 重新初始化 MCP 模块
            - 重新初始化浏览器工具
            - 重新初始化记忆系统
            - 重载 LLM 客户端配置
            - 热加载系统提示词（从 prompts.md）
        """
        GLOBAL_CONFIG.reload()
        
        current_model = self.llm_client.current_model_alias
        
        if self.agent_config:
            from agent.config.agent_config import AgentConfig
            agents_config = GLOBAL_CONFIG.get("agents", {})
            agent_config_dict = agents_config.get(self.agent_id, {})
            if agent_config_dict:
                new_config = AgentConfig.from_dict(self.agent_id, agent_config_dict)
                if new_config:
                    self.agent_config = new_config
                    if new_config.model:
                        current_model = new_config.model
        
        self.llm_client.reload_config()
        
        if current_model != self.llm_client.current_model_alias:
            switch_result = self.llm_client.switch_model(current_model)
            logger.info(f"{Fore.CYAN}[Reload] 模型已切换: {current_model}{Style.RESET_ALL}")
        
        self.file_tool = FileSystemTool(self.agent_config)
        self.shell_tool = ShellTool(self.agent_config)
        self.skill_loader.load_all_skills()
        self.tool_adapter = ToolAdapter(
            self.file_tool, 
            self.shell_tool, 
            self.skill_loader,
            delegation_depth=self.delegation_depth
        )
        self.conversation.reload_prompt()
        
        skill_patterns = self.agent_config.skills if self.agent_config else None
        skill_list_str = self.skill_loader.get_skill_list_info(skill_patterns)
        self.conversation.inject_skill_list(skill_list_str)
        
        if self.mcp_manager:
            try:
                self.mcp_manager.disconnect_all_sync()
            except Exception as e:
                logger.debug(f"[Reload] MCP 断开连接时出错（可忽略）: {e}")
        
        self._init_mcp()
        self._init_browser()
        self._init_memory()
        
        logger.info(f"{Fore.GREEN}✅ 所有组件已重载{Style.RESET_ALL}")

    def _detect_skill_from_input(self, user_input: str) -> Optional[str]:
        """
        从用户输入中检测是否指定了技能。
        
        检测逻辑:
            1. 精确匹配：检查用户输入是否包含技能名（支持多种变体）
            2. 关键词匹配：如果包含"skill"/"技能"/"使用"/"调用"等关键词，
               则检查输入中是否包含技能的某个部分
        
        Args:
            user_input: 用户输入文本
            
        Returns:
            检测到的技能名称，未检测到返回 None
        """
        if not user_input:
            return None
            
        user_input_lower = user_input.lower()
        
        for skill_name in self.skill_loader.skills.keys():
            skill_variants = [
                skill_name.lower(),
                skill_name.replace("-", " ").lower(),
                skill_name.replace("_", " ").lower(),
                skill_name.replace("-", "").lower(),
                skill_name.replace("_", "").lower(),
            ]
            for variant in skill_variants:
                if variant in user_input_lower:
                    return skill_name
        
        skill_keywords = ["skill", "技能", "使用", "调用"]
        has_skill_keyword = any(kw in user_input_lower for kw in skill_keywords)
        
        if has_skill_keyword:
            for skill_name in self.skill_loader.skills.keys():
                skill_parts = skill_name.replace("-", " ").replace("_", " ").split()
                for part in skill_parts:
                    if len(part) > 2 and part.lower() in user_input_lower:
                        return skill_name
        
        return None

    def _prepare_tools_for_skill(self, skill_name: Optional[str]) -> List[Dict[str, Any]]:
        """
        准备工具清单，如果指定了技能则将该技能工具置顶。
        
        Args:
            skill_name: 技能名称，为None时返回所有工具
            
        Returns:
            工具定义列表，格式符合OpenAI Function Calling规范
        """
        tools = self.tool_adapter.list_tools()
        
        if self.agent_config:
            allowed_patterns = self.agent_config.tools
            tools = self._filter_tools(tools, allowed_patterns)
            
            skill_patterns = self.agent_config.skills
            tools = self._filter_skills(tools, skill_patterns)
        
        if not skill_name:
            skill_name = self._detect_skill_from_input(None)
        
        if skill_name:
            skill_tool_name = f"skill_{skill_name}"
            skill_tool = None
            other_tools = []
            
            for tool in tools:
                tool_name = tool.get("function", {}).get("name", "")
                if tool_name == skill_tool_name:
                    skill_tool = tool
                else:
                    other_tools.append(tool)
            
            if skill_tool:
                tools = [skill_tool] + other_tools
        
        if self.agent_config and self.agent_config.sub_agents:
            from agent.tool.subagent_tool import get_subagent_tools_for_agent
            subagent_tools = get_subagent_tools_for_agent(
                self.agent_config, 
                self.delegation_depth
            )
            tools.extend(subagent_tools)
        
        return tools
    
    def _filter_tools(self, tools: List[Dict], patterns: List[str]) -> List[Dict]:
        """
        根据模式过滤工具（非技能工具）。
        
        Args:
            tools: 所有工具列表
            patterns: 允许的模式列表（支持通配符 *）
            
        Returns:
            过滤后的工具列表
        """
        import fnmatch
        
        if not patterns or "*" in patterns:
            return tools
        
        filtered = []
        for tool in tools:
            tool_name = tool.get("function", {}).get("name", "")
            
            if tool_name.startswith("skill_"):
                filtered.append(tool)
                continue
            
            for pattern in patterns:
                if pattern == "*":
                    filtered.append(tool)
                    break
                elif fnmatch.fnmatch(tool_name, pattern):
                    filtered.append(tool)
                    break
        
        return filtered
    
    def _filter_skills(self, tools: List[Dict], patterns: List[str]) -> List[Dict]:
        """
        根据模式过滤技能工具。
        
        Args:
            tools: 所有工具列表
            patterns: 允许的技能模式列表（支持通配符 *）
            
        Returns:
            过滤后的工具列表
        """
        import fnmatch
        
        if not patterns or "*" in patterns:
            return tools
        
        filtered = []
        for tool in tools:
            tool_name = tool.get("function", {}).get("name", "")
            
            if not tool_name.startswith("skill_"):
                filtered.append(tool)
                continue
            
            skill_name = tool_name[6:]
            
            for pattern in patterns:
                if pattern == "*":
                    filtered.append(tool)
                    break
                elif fnmatch.fnmatch(skill_name, pattern):
                    filtered.append(tool)
                    break
        
        return filtered

    def _process_tool_calls(self, message: Any) -> bool:  # type: ignore[return]
        """
        处理大模型返回的工具调用请求，支持技能文档动态注入。

        处理流程：
        1. 检查消息是否包含工具调用
        2. 将 assistant 的 tool_calls 消息添加到对话历史
        3. 遍历每个工具调用：
           - 如果是 skill_xxx 调用，获取技能文档并注入到 system prompt
           - 解析工具参数
           - 执行工具并记录结果
        4. 将工具执行结果添加到对话历史

        Args:
            message: 大模型返回的消息对象

        Returns:
            bool: 是否处理了工具调用（True=有工具调用，False=无工具调用）
        """
        if not hasattr(message, "tool_calls") or not message.tool_calls:
            return False

        logger.info(f"{Fore.CYAN}检测到工具调用请求，共 {len(message.tool_calls)} 个工具{Style.RESET_ALL}")
        logger.info(f"{Fore.CYAN}工具调用: {message.tool_calls or '无'}{Style.RESET_ALL}")

        tool_calls_list: List[Dict[str, Any]] = []
        for tc in message.tool_calls:
            tool_calls_list.append({
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments
                }
            })
        assistant_content = message.content or ""
        self.conversation.add_message(
            role="assistant",
            content=assistant_content,
            tool_calls=tool_calls_list
        )
        logger.info(f"{Fore.CYAN}已将 assistant 消息添加到对话历史，包含 {len(tool_calls_list)} 个工具调用{Style.RESET_ALL}")

        for idx, tool_call in enumerate(message.tool_calls, 1):
            tool_name = tool_call.function.name
            logger.info(f"{Fore.YELLOW}[{idx}/{len(message.tool_calls)}] 正在执行工具: {tool_name}{Style.RESET_ALL}")

            if not tool_name:
                error_msg = "错误：工具名称为空"
                logger.error(f"{Fore.RED}工具名称为空{Style.RESET_ALL}")
                self.conversation.add_tool_result(tool_call.id, "unknown", error_msg)
                continue

            try:
                arguments = json.loads(tool_call.function.arguments)
                logger.debug(f"工具参数: {json.dumps(arguments, ensure_ascii=False)}")
            except json.JSONDecodeError:
                error_msg = f"参数解析失败：{tool_call.function.arguments}"
                logger.error(f"{Fore.RED}工具 {tool_name} 参数解析失败: {error_msg}{Style.RESET_ALL}")
                self.conversation.add_tool_result(tool_call.id, tool_name, error_msg)
                continue

            if tool_name.startswith("skill_"):
                skill_name = tool_name.replace("skill_", "")
                
                if not self.conversation.has_injected_skill(skill_name):
                    self._inject_skill_document(skill_name)
                    logger.info(f"{Fore.CYAN}技能 '{skill_name}' 文档已注入 system prompt{Style.RESET_ALL}")
                
                if self._last_skill_call == tool_name:
                    self._last_skill_repeat_count += 1
                    
                    if self._last_skill_repeat_count >= self._max_skill_repeats:
                        self._blocked_skills.add(tool_name)
                        error_msg = f"错误：技能 '{skill_name}' 已被调用过，文档已在 system prompt 中。该技能工具已被临时禁用，请直接调用文档中指定的工具（如 shell_exec）来完成任务。"
                        logger.warning(f"{Fore.RED}⚠ 检测到第 {self._last_skill_repeat_count + 1} 次重复调用技能: {tool_name}，已阻止该技能工具{Style.RESET_ALL}")
                        self.conversation.add_tool_result(tool_call.id, tool_name, error_msg)
                        continue
                    else:
                        warning_msg = f"⚠ 警告：请勿重复调用 '{tool_name}'。技能文档已注入 system prompt，请直接执行文档中的工具调用。"
                        logger.warning(f"{Fore.YELLOW}⚠ 检测到第 {self._last_skill_repeat_count + 1} 次重复调用技能: {tool_name}，请勿再调用{Style.RESET_ALL}")
                        self.conversation.add_tool_result(tool_call.id, tool_name, warning_msg)
                        continue
                else:
                    self._last_skill_call = tool_name
                    self._last_skill_repeat_count = 0

            
            tool_start_time = time.time()
            
            tool_result = self.tool_adapter.call_tool(tool_name, arguments)
            
            if tool_name == "search_memory" and tool_result.get("status") == "success":
                data = tool_result.get("data", {})
                memories = data.get("memories", [])
                self.conversation.inject_memories(memories)
                if memories:
                    logger.info(f"{Fore.CYAN}[记忆注入] 已将 {len(memories)} 条记忆注入到 system prompt{Style.RESET_ALL}")
                else:
                    logger.info(f"{Fore.CYAN}[记忆注入] 查询结果为空，已清理记忆占位符{Style.RESET_ALL}")
            
            tool_elapsed = time.time() - tool_start_time
            result_status = tool_result.get("status", "unknown")
            
            args_summary = str(arguments)[:100] + "..." if len(str(arguments)) > 100 else str(arguments)
            logger.info(f"[工具调用] {tool_name}, 参数: {args_summary}, 状态: {result_status}, 耗时: {tool_elapsed:.2f}s")
            
            if result_status == "success":
                logger.info(f"{Fore.GREEN}✓ 工具 {tool_name} 执行成功{Style.RESET_ALL}")
            else:
                logger.warning(f"{Fore.RED}✗ 工具 {tool_name} 执行失败: {tool_result.get('message', '未知错误')}{Style.RESET_ALL}")

            self.conversation.add_tool_result(
                tool_call.id,
                tool_name,
                json.dumps(tool_result, ensure_ascii=False, indent=2)
            )

        print_conversation_history(self.conversation.get_messages(), max_content_length=88888,print_last_only=True)
        logger.info(f"{Fore.CYAN}=================================={Style.RESET_ALL}")
        logger.info(f"{Fore.CYAN}所有工具调用完成，继续生成回答...{Style.RESET_ALL}")
        
        # 明确返回 True 表示已处理工具调用
        return True

    def _inject_skill_document(self, skill_name: str) -> bool:
        """
        从 SkillLoader 获取完整技能文档并注入到 system prompt。

        Args:
            skill_name: 技能名称

        Returns:
            bool: 注入是否成功
        """
        try:
            skill_info = self.skill_loader.get_skill_info(skill_name)
            if not skill_info:
                logger.error(f"{Fore.RED}技能 '{skill_name}' 不存在，无法注入文档{Style.RESET_ALL}")
                return False

            full_content = skill_info.get("full_content", "")
            if not full_content:
                logger.error(f"{Fore.RED}技能 '{skill_name}' 没有完整文档内容{Style.RESET_ALL}")
                return False

            skill_doc = f"""{full_content}

            ---
            ## 重要提示
            - 你是智能助手，正在执行技能「{skill_name}」
            - 请严格按照上述文档中的指导调用具体工具来完成任务
            - 不要只返回说明，必须调用工具来实际执行任务
            - 任务完成后，系统会自动清理该技能文档
            """

            success = self.conversation.inject_skill_document(skill_name, skill_doc)

            if success:
                logger.info(f"{Fore.GREEN}✓ 技能 '{skill_name}' 文档已注入 system prompt{Style.RESET_ALL}")
            else:
                logger.warning(f"{Fore.YELLOW}⚠ 技能 '{skill_name}' 文档注入失败{Style.RESET_ALL}")

            return success

        except Exception as e:
            logger.error(f"{Fore.RED}技能文档注入过程出错: {str(e)}{Style.RESET_ALL}")
            return False

    async def chat_stream(self, user_input: str) -> AsyncGenerator[str, None]:
        """
        模拟流式对话方法。

        参数：
            user_input: 用户输入的对话内容

        返回：
            AsyncGenerator[str, None]: 流式输出生成器（空实现）
        """
        if False:
            yield ""

    def chat(self, user_input: str, delegation_depth: Optional[int] = None) -> dict:
        """
        非流式对话方法（用于CLI和API调用），支持技能文档动态注入。

        Args:
            user_input: 用户输入
            delegation_depth: 委托深度（覆盖实例级别），用于子代理调用

        Returns:
            dict: 包含 content, elapsed_time, total_prompt_tokens, total_completion_tokens
        """
        if delegation_depth is not None:
            self.delegation_depth = delegation_depth
        
        start_time = time.time()
        total_prompt_tokens = 0
        total_completion_tokens = 0
        
        self.conversation.add_message(role="user", content=user_input)
        
        input_summary = user_input[:50] + "..." if len(user_input) > 50 else user_input
        logger.info(f"[对话开始] 会话: {self.conversation.session_id}, 输入: {input_summary}")
        
        print_conversation_history(self.conversation.get_messages(), max_content_length=88888, print_last_only=True)
        current_tool_calls = 0

        detected_skill = self._detect_skill_from_input(user_input)
        if detected_skill:
            logger.info(f"[技能检测] 检测到指定技能: {detected_skill}")
            logger.info(f"[技能检测] 使用指定技能: {detected_skill}")

        tools = self._prepare_tools_for_skill(detected_skill)
        logger.debug(f"[工具准备] 工具数: {len(tools)}")
        
        logger.debug(f"[工具准备] 工具列表：")
        for tool in tools:
            logger.debug(f"工具名: {tool}")
        logger.info(f"系统提示词: {self.conversation.system_prompt}")

        while current_tool_calls < self.max_tool_calls:
            current_tool_calls += 1
            logger.debug(f"[LLM调用] 第 {current_tool_calls} 轮, 消息数: {len(self.conversation.get_messages())}")
            logger.info(f"[第 {current_tool_calls} 轮] 调用大模型...")
                
            try:
                response = self.llm_client.chat_completion(
                    messages=self.conversation.get_messages(),
                    tools=tools,
                    stream=False
                )
                
                if hasattr(response, 'usage') and response.usage:
                    total_prompt_tokens += response.usage.prompt_tokens or 0
                    total_completion_tokens += response.usage.completion_tokens or 0
                    logger.info(f"[LLM响应] Token消耗: prompt={response.usage.prompt_tokens}, completion={response.usage.completion_tokens}, 累计: prompt={total_prompt_tokens}, completion={total_completion_tokens}")
            except Exception as e:
                logger.error(f"[LLM错误] {str(e)}")
                self.conversation.clear_injected_document()
                self._last_skill_call = None
                self._last_skill_repeat_count = 0
                
                self.conversation.cleanup_tool_messages()
                
                context_window = self.llm_client.get_context_window()
                context_tokens = self.llm_client.count_tokens(self.conversation.get_messages())
                context_usage_percent = (context_tokens / context_window * 100) if context_window > 0 else 0
                total_tokens = total_prompt_tokens + total_completion_tokens
                elapsed = time.time() - start_time
                context_window_display = f"{context_window // 1000}k" if context_window >= 1000 else str(context_window)

                logger.error(f"大模型调用失败：{str(e)}")
                logger.debug(f"📊 耗时: {elapsed:.2f}s | 输入: {total_prompt_tokens} | 输出: {total_completion_tokens} | 总计: {total_tokens}")
                logger.debug(f"📋 上下文: {context_usage_percent:.1f}% of {context_window_display}")

                return {
                    "content": f"大模型调用失败：{str(e)}",
                    "elapsed_time": elapsed,
                    "total_prompt_tokens": total_prompt_tokens,
                    "total_completion_tokens": total_completion_tokens,
                    "total_tokens": total_tokens,
                    "context_window": context_window,
                    "context_usage_percent": context_usage_percent
                }

            choice = response.choices[0]
            message = choice.message

            reasoning_content = None
            reasoning_tokens = None
            
            reasoning_content = getattr(message, 'reasoning_content', None)
            if not reasoning_content:
                reasoning_content = getattr(message, 'thinking_content', None)
            if not reasoning_content:
                reasoning_content = getattr(message, 'thoughts', None)
            if not reasoning_content:
                thinking_blocks = getattr(message, 'thinking', None)
                if thinking_blocks and hasattr(thinking_blocks, '__iter__'):
                    try:
                        reasoning_content = '\n'.join([
                            block.text if hasattr(block, 'text') else str(block)
                            for block in thinking_blocks
                        ])
                    except:
                        pass
            
            if hasattr(response, 'usage') and response.usage:
                if hasattr(response.usage, 'completion_tokens_details'):
                    reasoning_tokens = getattr(response.usage.completion_tokens_details, 'reasoning_tokens', None)
            
            if reasoning_content:
                logger.info(f"[思考过程] 模型进行了推理思考:")
                print(f"\n{Fore.CYAN}{'='*60}")
                print(f"🧠 思考过程 (reasoning_content):")
                print(f"{'='*60}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}{reasoning_content}{Style.RESET_ALL}")
                print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
            elif reasoning_tokens and reasoning_tokens > 0:
                logger.info(f"[思考过程] 模型使用了 {reasoning_tokens} 个推理 token (内容未公开)")
                print(f"\n{Fore.CYAN}{'='*60}")
                print(f"🧠 思考过程: 模型内部进行了 {reasoning_tokens} tokens 的推理")
                print(f"   (推理内容不对外公开，仅显示 token 数量)")
                print(f"{'='*60}{Style.RESET_ALL}\n")

            if not self._process_tool_calls(message):
                self.conversation.add_message(role="assistant", content=message.content)
                
                elapsed = time.time() - start_time
                response_len = len(message.content) if message.content else 0
                logger.info(f"[对话结束] 会话: {self.conversation.session_id}, 回答长度: {response_len}, 耗时: {elapsed:.2f}s")
                logger.info(f"[完成] 回答生成完成:{message.content}")

                if self.conversation.has_injected_skill():
                    self.conversation.clear_injected_document()
                self._last_skill_call = None
                self._last_skill_repeat_count = 0

                self.conversation.cleanup_tool_messages()

                if self._auto_save:
                    self.conversation.save()
                
                context_window = self.llm_client.get_context_window()
                context_tokens = self.llm_client.count_tokens(self.conversation.get_messages())
                context_usage_percent = (context_tokens / context_window * 100) if context_window > 0 else 0
                total_tokens = total_prompt_tokens + total_completion_tokens
                context_window_display = f"{context_window // 1000}k" if context_window >= 1000 else str(context_window)

                logger.debug(f"✓ 回答完成")
                logger.debug(f"📊 耗时: {elapsed:.2f}s | 输入: {total_prompt_tokens} | 输出: {total_completion_tokens} | 总计: {total_tokens}")
                logger.debug(f"📋 上下文: {context_usage_percent:.1f}% of {context_window_display}")

                return {
                    "content": message.content or "",
                    "reasoning_content": reasoning_content,
                    "elapsed_time": elapsed,
                    "total_prompt_tokens": total_prompt_tokens,
                    "total_completion_tokens": total_completion_tokens,
                    "total_tokens": total_tokens,
                    "context_window": context_window,
                    "context_usage_percent": context_usage_percent
                }

        if self.conversation.has_injected_skill():
            self.conversation.clear_injected_document()
        self._last_skill_call = None
        self._last_skill_repeat_count = 0

        self.conversation.cleanup_tool_messages()

        if self._auto_save:
            self.conversation.save()
        
        context_window = self.llm_client.get_context_window()
        context_tokens = self.llm_client.count_tokens(self.conversation.get_messages())
        context_usage_percent = (context_tokens / context_window * 100) if context_window > 0 else 0
        total_tokens = total_prompt_tokens + total_completion_tokens
        elapsed = time.time() - start_time
        context_window_display = f"{context_window // 1000}k" if context_window >= 1000 else str(context_window)

        logger.warning(f"[对话结束] 会话: {self.conversation.session_id}, 原因: 达到最大工具调用轮数")
        logger.warning("[警告] 达到最大工具调用轮数")
        logger.debug(f"📊 耗时: {elapsed:.2f}s | 输入: {total_prompt_tokens} | 输出: {total_completion_tokens} | 总计: {total_tokens}")
        logger.debug(f"📋 上下文: {context_usage_percent:.1f}% of {context_window_display}")

        return {
            "content": "已达到最大工具调用轮数，无法继续执行",
            "elapsed_time": elapsed,
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
            "context_window": context_window,
            "context_usage_percent": context_usage_percent
        }
