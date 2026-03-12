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
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, TYPE_CHECKING, Union

from colorama import Fore, Style
from loguru import logger

from agent.config.configloader import GLOBAL_CONFIG
from agent.core.conversation import ConversationManager
from agent.core.agent_initializer import AgentInitializer
from agent.core.token_counter import TokenCounter
from agent.fileSystem.filesystem import FileSystemTool
from agent.provider.llmclient import LLMClient
from agent.skill.skill_loader import SkillLoader
from agent.memory import MemorySystem
from agent.tool.shelltool import ShellTool
from agent.tool.tooladapter import ToolAdapter
from agent.utils import words_utils


if TYPE_CHECKING:
    from agent.config.agent_config import AgentConfig


def _format_content_for_print(content, max_length: int = 100) -> str:
    """格式化消息内容，截断 Base64 图片数据。"""
    if isinstance(content, str):
        return content[:max_length] + ('...' if len(content) > max_length else '')
    
    if not isinstance(content, list):
        return str(content)[:max_length]
    
    parts = []
    for item in content:
        if not isinstance(item, dict):
            parts.append(str(item)[:max_length])
            continue
        item_type = item.get('type')
        if item_type == 'text':
            text = item.get('text', '')[:max_length]
            parts.append(text + ('...' if len(item.get('text', '')) > max_length else ''))
        elif item_type == 'image_url':
            url = item.get('image_url', {}).get('url', '')
            if url.startswith('data:'):
                mime = url[5:url.find(';base64,')] if ';base64,' in url else 'unknown'
                parts.append(f"[图片:{mime},{len(url)}字符]")
            else:
                parts.append(f"[图片URL:{url[:30]}...]")
        else:
            parts.append(str(item)[:max_length])
    return ' '.join(parts)


def _extract_reasoning_content(message: Any) -> Optional[str]:
    """
    从大模型消息中提取推理/思考内容。
    
    支持多种字段名:
        - reasoning_content: 通义千问等模型
        - thinking_content: 某些模型
        - thoughts: 某些模型
        - thinking: 块状思考内容
    
    Args:
        message: 大模型返回的消息对象
    
    Returns:
        Optional[str]: 提取的思考内容，无则返回 None
    """
    reasoning_content = getattr(message, 'reasoning_content', None)
    if reasoning_content:
        return reasoning_content
    
    reasoning_content = getattr(message, 'thinking_content', None)
    if reasoning_content:
        return reasoning_content
    
    reasoning_content = getattr(message, 'thoughts', None)
    if reasoning_content:
        return reasoning_content
    
    thinking_blocks = getattr(message, 'thinking', None)
    if thinking_blocks and hasattr(thinking_blocks, '__iter__'):
        try:
            return '\n'.join([
                block.text if hasattr(block, 'text') else str(block)
                for block in thinking_blocks
            ])
        except Exception:
            pass
    
    return None


def print_conversation_history(messages: list, max_content_length: int = 100, print_last_only: bool = False):
    """
    打印对话历史信息（全局工具函数）。

    功能说明:
        - 格式化打印对话消息列表
        - 支持不同角色的颜色区分
        - 支持只打印最后一条消息
        - 自动截断 Base64 图片数据

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
        formatted_content = _format_content_for_print(content, max_content_length)
        
        if role == 'system':
            logger.debug(f"{Fore.MAGENTA}[历史 {idx}] system: {formatted_content}{Style.RESET_ALL}")
        elif role == 'user':
            logger.debug(f"{Fore.YELLOW}[历史 {idx}] user: {formatted_content}{Style.RESET_ALL}")
        elif role == 'assistant':
            if tool_calls:
                tool_names = [tc.get('function', {}).get('name', 'unknown') for tc in tool_calls]
                logger.debug(f"{Fore.GREEN}[历史 {idx}] assistant(tool): {tool_names}{Style.RESET_ALL}")
            else:
                logger.debug(f"{Fore.GREEN}[历史 {idx}] assistant: {formatted_content}{Style.RESET_ALL}")
        elif role == 'tool':
            logger.debug(f"{Fore.BLUE}[历史 {idx}] tool({tool_call_id}): {formatted_content}{Style.RESET_ALL}")
        else:
            logger.debug(f"{Fore.WHITE}[历史 {idx}] {role}: {formatted_content}{Style.RESET_ALL}")


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
        - 支持任务拆解和断点续跑
    
    核心方法:
        - chat: 非流式对话（用于CLI和API）
        - chat_stream: 流式对话（用于旧API兼容）
        - reload: 重载所有组件配置
    
    配置项:
        - max_tool_calls: 最大工具调用次数，默认10次
        - agent_config: Agent配置对象，支持多Agent架构
        - delegation_depth: 当前委托深度，用于子代理调用
    """
    
    mcp_manager: Any
    mcp_tool_adapter: Any
    browser_tool: Any
    memory_system: Any
    task_decomposer: Any
    task_tree_manager: Any
    heartbeat_manager: Any
    
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
        
        if agent_config and agent_config.model:
            self.llm_client = LLMClient(default_model=agent_config.model)
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
        
        AgentInitializer.init_mcp(self)
        AgentInitializer.init_browser(self)
        AgentInitializer.init_memory(self)
        AgentInitializer.init_task_decomposition(self)

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
        
        if self.agent_config:
            llm_params = self.agent_config.get_llm_params()
            self.llm_client.apply_preset(llm_params)
            logger.info(f"{Fore.CYAN}[Reload] LLM 参数已更新: temperature={llm_params.get('temperature')}, max_tokens={llm_params.get('max_tokens')}, timeout={llm_params.get('timeout')}{Style.RESET_ALL}")
        
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
        
        if self.mcp_manager:
            try:
                self.mcp_manager.disconnect_all_sync()
            except Exception as e:
                logger.debug(f"[Reload] MCP 断开连接时出错（可忽略）: {e}")
        
        AgentInitializer.init_mcp(self)
        AgentInitializer.init_browser(self)
        AgentInitializer.init_memory(self)
        
        logger.info(f"{Fore.GREEN}✅ 所有组件已重载{Style.RESET_ALL}")

    def _clear_skill_state(self):
        """
        清理技能状态（注入文档、重复计数等）
        """
        if self.conversation.has_injected_skill():
            self.conversation.clear_injected_document()
        self._last_skill_call = None
        self._last_skill_repeat_count = 0
    
    def _get_core_tool_names(self) -> List[str]:
        """
        获取核心工具名称列表（始终加载）
        
        从 tool_index.json 中读取 category="core" 的工具。
        如果 memory_system 未初始化，则使用默认的核心工具列表。
        
        Returns:
            核心工具名称列表
        """
        default_core_tools = [
        ]
        
        if not self.memory_system:
            return default_core_tools
        
        try:
            data = self.memory_system._read_tool_index()
            tools = data.get("tools", [])
            core_names = [t["name"] for t in tools if t.get("category") == "core" and t.get("enabled", True)]
            
            if core_names:
                return core_names
            return default_core_tools
        except Exception as e:
            logger.warning(f"读取核心工具列表失败，使用默认值: {e}")
            return default_core_tools
    
    def _get_core_tools(self) -> List[Dict[str, Any]]:
        """
        获取核心工具列表（始终加载）
        
        Returns:
            核心工具定义列表
        """
        core_names = set(self._get_core_tool_names())
        core_tools = []
        
        for name in core_names:
            if name in self.tool_adapter.tools:
                tool_info = self.tool_adapter.tools[name]
                core_tools.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool_info["description"],
                        "parameters": tool_info["parameters"]
                    }
                })
        
        return core_tools
    
    def _preprocess_user_input(self, user_input: Union[str, List[str]]) -> List[str]:
        """
        预处理用户输入，预测可能需要的工具
        
        支持单个查询和批量查询：
        - 字符串输入：自动分句后批量查询
        - 列表输入：直接批量查询
        
        流程：
        1. 从记忆索引搜索相关工具
        2. 自动注册到工具列表
        3. 返回注册的工具名称
        
        Args:
            user_input: 用户输入（字符串或字符串列表）
        
        Returns:
            注册的工具名称列表（去重）
        """
        logger.info(f"[预处理] 开始预处理, memory_system={self.memory_system is not None}")
        
        if not self.memory_system:
            logger.warning("[预处理] memory_system 为 None，跳过预测")
            return []
        
        memory_config = GLOBAL_CONFIG.get("memory", {})
        tool_search_config = memory_config.get("tool_search", {})
        
        top_k = tool_search_config.get("top_k", 3)
        distance_threshold = tool_search_config.get("distance_threshold", 1.0)
        
        logger.info(f"[预处理] 配置: top_k={top_k}, distance_threshold={distance_threshold}")
        
        try:
            if isinstance(user_input, list):
                queries = user_input
                if not queries:
                    return []
                logger.info(f"[预处理] 列表输入模式，查询数量: {len(queries)}")
            else:
                queries = words_utils.fast_chinese_task_split(user_input)
                logger.info(f"[预处理] 字符串分句结果: {queries}")
                if not queries:
                    return []
            
            tools = self.tool_adapter._run_async(
                self.memory_system.search_tools_batch(queries, top_k=top_k, distance_threshold=distance_threshold)
            )
            
            logger.debug(f"[预处理] 搜索返回 {len(tools)} 个工具")
            
            registered = []
            seen_names = set()
            for tool_def in tools:
                func_def = tool_def.get("function", tool_def)
                tool_name = func_def.get("name", "")
                if tool_name and tool_name not in seen_names:
                    if self.tool_adapter._register_skill_tool(tool_name, func_def):
                        registered.append(tool_name)
                        seen_names.add(tool_name)
                        logger.info(f"[预处理] 预测加载工具: {tool_name}")
            
            return registered
        except Exception as e:
            logger.warning(f"[预处理] 工具预测失败: {e}")
            return []
    
    def _prepare_tools_with_preprocess(self, user_input: str) -> List[Dict[str, Any]]:
        """
        准备工具列表（核心工具 + 预测工具）
        
        Args:
            user_input: 用户输入
        
        Returns:
            工具定义列表
        """
        core_tools = self._get_core_tools()
        core_names = {t["function"]["name"] for t in core_tools}
        
        predicted_names = self._preprocess_user_input(user_input)
        
        predicted_tools = []
        for name in predicted_names:
            if name not in core_names and name in self.tool_adapter.tools:
                tool_info = self.tool_adapter.tools[name]
                predicted_tools.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool_info["description"],
                        "parameters": tool_info["parameters"]
                    }
                })
        
        all_tools = core_tools + predicted_tools
        
        if self.agent_config and self.agent_config.sub_agents:
            from agent.tool.subagent_tool import get_subagent_tools_for_agent
            subagent_tools = get_subagent_tools_for_agent(
                self.agent_config, 
                self.delegation_depth
            )
            all_tools.extend(subagent_tools)
        
        logger.info(f"[工具准备] 核心={len(core_tools)}, 预测={len(predicted_tools)}, 总计={len(all_tools)}")
        
        return all_tools

    def _check_pending_task(self) -> Optional[Dict]:
        """
        检查是否有未完成任务（代码判断）
        
        Returns:
            未完成任务信息字典，无则返回 None
        """
        if not self.heartbeat_manager:
            return None
        
        pending_info = self.heartbeat_manager.has_pending_task()
        if not pending_info:
            return None
        
        task_id = pending_info.get("task_id")
        if not task_id:
            return None
        
        task_tree = self.task_tree_manager.load(task_id)
        if not task_tree:
            return None
        
        heartbeat = self.heartbeat_manager.load()
        if not heartbeat:
            return None
        
        completed_steps = heartbeat.get("completed_steps", [])
        current_step = self.task_tree_manager.get_current_step(task_id, heartbeat)
        
        return {
            "task_id": task_id,
            "task_goal": task_tree.get("task_goal", ""),
            "progress": f"{len(completed_steps)}/{heartbeat.get('total_steps', 0)}",
            "current_step": current_step,
            "status": pending_info.get("status", "")
        }

    def _get_completed_results(self, task_id: str) -> List[Dict]:
        """
        获取已完成步骤的结果（用于执行阶段注入）
        
        Args:
            task_id: 任务 ID
        
        Returns:
            已完成步骤结果列表
        """
        heartbeat = self.heartbeat_manager.load()
        if not heartbeat:
            return []
        
        completed_steps = set(heartbeat.get("completed_steps", []))
        if not completed_steps:
            return []
        
        results_data = self.task_tree_manager.load_results(task_id)
        if not results_data:
            return []
        
        completed_results = []
        for result in results_data.get("results", []):
            if result.get("step_id") in completed_steps:
                completed_results.append({
                    "step_id": result.get("step_id"),
                    "step_desc": result.get("step_desc", ""),
                    "tool_name": result.get("tool_name", ""),
                    "summary": self._summarize_result(result.get("result", {}))
                })
        
        return completed_results

    def _format_previous_results(self, task_id: str, completed_steps: set) -> str:
        """
        格式化前置结果为简洁字符串
        
        Args:
            task_id: 任务 ID
            completed_steps: 已完成步骤 ID 集合
        
        Returns:
            格式化的前置结果字符串
        """
        if not completed_steps:
            return ""
        
        results_data = self.task_tree_manager.load_results(task_id)
        if not results_data:
            return ""
        
        formatted = []
        for result in results_data.get("results", []):
            step_id = result.get("step_id", "")
            if step_id in completed_steps:
                summary = self._summarize_result(result.get("result", {}), max_length=100)
                formatted.append(f"[{step_id}] {summary}")
        
        return "\n".join(formatted) if formatted else ""

    def _summarize_result(self, result: Dict, max_length: int = 200) -> str:
        """
        总结执行结果
        
        Args:
            result: 执行结果字典
            max_length: 最大长度
        
        Returns:
            结果摘要字符串
        """
        if not result:
            return "无结果"
        
        if isinstance(result, dict):
            if "content" in result:
                content = str(result["content"])
                return content[:max_length] + "..." if len(content) > max_length else content
            if "status" in result:
                return f"状态: {result['status']}"
        
        return str(result)[:max_length]

    def _execute_by_task_type(self, task_tree: Dict, user_input: str, counter: TokenCounter) -> dict:
        """
        根据 task_type 执行不同流程
        
        Args:
            task_tree: 任务树字典（包含 prompt_tokens 和 completion_tokens）
            user_input: 用户输入
            counter: TokenCounter 实例
        
        Returns:
            执行结果字典
        """
        task_type = task_tree.get("task_type", "new_task")
        
        if task_type == "continue":
            return self._resume_task(counter)
        
        return self._execute_task_tree(task_tree, user_input, counter)

    def _resume_task(self, counter: TokenCounter) -> dict:
        """
        继续执行未完成任务
        
        Args:
            counter: TokenCounter 实例
        
        Returns:
            执行结果字典
        """
        if not self.heartbeat_manager or not self.task_tree_manager:
            return counter.build_result("任务拆解模块未初始化")
        
        heartbeat = self.heartbeat_manager.load()
        if not heartbeat:
            return counter.build_result("没有未完成的任务")
        
        task_id = heartbeat.get("task_id")
        task_tree = self.task_tree_manager.load(task_id)
        
        if not task_tree:
            return counter.build_result("任务树加载失败")
        
        logger.info(f"{Fore.CYAN}[断点续跑] 恢复任务: {task_id}{Style.RESET_ALL}")
        
        return self._execute_task_with_tree(task_tree, task_id, counter)

    def _execute_task_tree(self, task_tree: Dict, user_input: str, counter: TokenCounter) -> dict:
        """
        执行任务树（新任务）
        
        如果有未完成任务，会先放弃旧任务再创建新任务。
        
        Args:
            task_tree: 任务树字典（包含 prompt_tokens 和 completion_tokens）
            user_input: 用户输入
            counter: TokenCounter 实例
        
        Returns:
            执行结果字典
        """
        counter.add_tokens(
            task_tree.get("prompt_tokens", 0),
            task_tree.get("completion_tokens", 0)
        )
        
        if not self.task_tree_manager or not self.heartbeat_manager:
            logger.warning(f"{Fore.YELLOW}[任务执行] 任务拆解模块未初始化，回退到普通对话{Style.RESET_ALL}")
            result = self._original_chat(user_input)
            counter.add_tokens(
                result.get("total_prompt_tokens", 0),
                result.get("total_completion_tokens", 0)
            )
            return counter.build_result(result.get("content", ""))
        
        heartbeat = self.heartbeat_manager.load()
        if heartbeat and heartbeat.get("task_id"):
            old_task_id = heartbeat.get("task_id")
            self.task_tree_manager.update_task_status(old_task_id, "abandoned")
            self.heartbeat_manager.clear()
            logger.info(f"{Fore.CYAN}[任务切换] 已放弃旧任务: {old_task_id}{Style.RESET_ALL}")
        
        task_id = self.task_tree_manager.generate_task_id()
        
        self.task_tree_manager.save(task_id, task_tree)
        self.heartbeat_manager.init(task_id, task_tree)
        
        logger.info(f"{Fore.CYAN}[任务执行] 创建新任务: {task_id}{Style.RESET_ALL}")
        
        return self._execute_task_with_tree(task_tree, task_id, counter)

    def _execute_task_with_tree(self, task_tree: Dict, task_id: str, counter: TokenCounter) -> dict:
        """
        执行任务树（核心执行逻辑）
        
        Args:
            task_tree: 任务树字典
            task_id: 任务 ID
            counter: TokenCounter 实例
        
        Returns:
            执行结果字典
        """
        while True:
            heartbeat = self.heartbeat_manager.load()
            if not heartbeat:
                break
            
            if heartbeat.get("status") == "completed":
                logger.info(f"{Fore.GREEN}[任务完成] 任务 {task_id} 已完成{Style.RESET_ALL}")
                break
            
            completed_steps = heartbeat.get("completed_steps", [])
            current_step = self.task_tree_manager.get_runnable_step(task_id, completed_steps)
            
            if not current_step:
                logger.info(f"{Fore.CYAN}[任务执行] 无可执行步骤，任务可能已完成{Style.RESET_ALL}")
                break
            
            step_id = current_step.get("step_id")
            required_abilities = current_step.get("required_abilities", [])
            
            if "continue" in required_abilities:
                self.heartbeat_manager.start_step(step_id)
                self.heartbeat_manager.complete_step(step_id)
                self.task_tree_manager.update_step_status(task_id, step_id, "completed")
                continue
            
            task_context = {
                "task_goal": task_tree.get("task_goal", ""),
                "total_steps": task_tree.get("total_steps", 0),
                "completed_steps": len(completed_steps),
                "current_step": current_step,
                "next_step_desc": self._get_next_step_desc(task_tree, completed_steps)
            }
            
            self.conversation.inject_task_context(task_context)
            
            self.heartbeat_manager.start_step(step_id)
            
            tools = self._prepare_tools_for_ability_match(required_abilities)
            
            step_index = len(completed_steps) + 1
            previous_results = self._format_previous_results(task_id, set(completed_steps))
            
            step_result = self._execute_step_with_tools(
                current_step, 
                tools, 
                task_tree,
                step_index,
                previous_results
            )
            
            counter.add_tokens(
                step_result.get("prompt_tokens", 0),
                step_result.get("completion_tokens", 0)
            )
            
            if step_result.get("success"):
                self.task_tree_manager.update_step_status(task_id, step_id, "completed")
                self.heartbeat_manager.complete_step(step_id)
                self.task_tree_manager.save_step_result(
                    task_id, 
                    step_id, 
                    step_result.get("tool_name", ""),
                    step_result.get("arguments", {}),
                    step_result.get("result", {})
                )
            else:
                self.task_tree_manager.increment_retry(task_id, step_id)
                self.task_tree_manager.update_step_status(
                    task_id, 
                    step_id, 
                    "failed",
                    step_result.get("error")
                )
                self.heartbeat_manager.fail_step(step_id, step_result.get("error", "未知错误"))
                logger.warning(f"{Fore.YELLOW}[任务执行] 步骤 {step_id} 失败: {step_result.get('error')}{Style.RESET_ALL}")
            
            with self.conversation._lock:
                self.conversation._working_messages.clear()
            
            self.conversation.clear_task_context()
            self.conversation.clear_injected_document()
        
        task_tree = self.task_tree_manager.load(task_id)
        final_status = task_tree.get("status", "unknown") if task_tree else "unknown"
        
        if final_status in ["completed", "partial_completed"]:
            self.heartbeat_manager.clear()
            
            summary_result = self._summarize_task_results(task_id, task_tree, counter)
            
            if final_status == "partial_completed":
                failed_steps = [s for s in task_tree.get("task_tree", []) if s.get("status") == "failed"]
                failed_info = "\n".join([f"- {s.get('step_id')}: {s.get('error_message', '未知错误')}" for s in failed_steps])
                summary_result["content"] = f"{summary_result.get('content', '')}\n\n⚠️ 部分步骤执行失败:\n{failed_info}"
            
            self.conversation.add_message(role="assistant", content=summary_result.get("content", ""))
            self.conversation.finalize_conversation(save_user_message=False)
            
            if self._auto_save:
                self.conversation.save()
            
            return summary_result
        else:
            self.conversation.cancel_conversation()
            return counter.build_result(f"任务执行中断，状态: {final_status}")

    def _summarize_task_results(self, task_id: str, task_tree: Dict, counter: TokenCounter) -> dict:
        """
        汇总任务执行结果
        
        Args:
            task_id: 任务 ID
            task_tree: 任务树
            counter: TokenCounter 实例
        
        Returns:
            汇总结果字典
        """
        results_data = self.task_tree_manager.load_results(task_id)
        
        if not results_data:
            return counter.build_result(f"任务执行完成: {task_tree.get('task_goal', '')}")
        
        all_step_contents = []
        all_results = []
        for step_result in results_data.get("results", []):
            result = step_result.get("result", {})
            content = result.get("content", "")
           
            
            if content:
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict):
                        actual_content = parsed.get("content", "")
                        if actual_content:
                            all_step_contents.append(f"[{step_result.get('step_id', '')}] {actual_content}")
                            all_results.append(actual_content)
                        else:
                            all_step_contents.append(f"[{step_result.get('step_id', '')}] {content}")
                            all_results.append(content)
                            
                    else:
                        all_step_contents.append(f"[{step_result.get('step_id', '')}] {content}")
                        all_results.append(content)
                except (json.JSONDecodeError, TypeError):
                    all_step_contents.append(f"[{step_result.get('step_id', '')}] {content}")
                    all_results.append(content)
        
        if not all_step_contents:
            return counter.build_result(f"任务执行完成: {task_tree.get('task_goal', '')}")
        
        task_goal = task_tree.get("task_goal", "")
        summary_prompt = f"""用户的原始请求：{task_goal}
            执行结果：
            {chr(10).join(all_step_contents)}
            
            请根据用户的原始请求来决定回复方式：
            - 如果用户要求简短回复，请简洁回答
            - 如果用户要求详细报告，请详细说明
            - 如果用户要求总结，请给出总结
            - 如果用户没有特别要求，用自然友好的语气告诉用户你完成了什么
            
            直接回复用户，不要解释你的回复方式。"""
        
        try:
            # 如果只有一步，直接返回内容
            
            if len(all_step_contents) > 1:
                logger.debug(f"\n{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}")
                logger.debug(f"{Fore.MAGENTA}📤 [任务汇总] 请求消息:{Style.RESET_ALL}")
                logger.debug(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}")
                logger.debug(f"{Fore.YELLOW}{summary_prompt}{Style.RESET_ALL}")
                logger.debug(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}\n")
        
                response = self.llm_client.chat_completion(
                messages=[{"role": "user", "content": summary_prompt}],
                stream=False)
                counter.add_usage(response)
            
                summary_content = response.choices[0].message.content or ""
            else:
                summary_content = re.sub(r'^\[step_\d+\]\s*', '', all_results[0] or "")
                
            logger.debug(f"[任务汇总] 生成总结成功")
            print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
            print(f"{Fore.GREEN}🤖 任务汇总回答:{Style.RESET_ALL}")
            print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
            print(summary_content)
            print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}\n")
            
            return counter.build_result(summary_content)
        except Exception as e:
            logger.error(f"[任务汇总] 生成总结失败: {e}")
            return counter.build_result(f"任务执行完成: {task_goal}\n\n执行结果:\n" + "\n".join(all_step_contents))

    def _prepare_tools_for_ability_match(self, required_abilities: List[str]) -> List[Dict]:
        """
        根据能力需求准备工具列表
        
        Args:
            required_abilities: 所需能力列表
        
        Returns:
            工具定义列表
        """
        core_tools = self._get_core_tools()
        
        if self.memory_system:
            for ability in required_abilities:
                if ability not in ["llm_response", "continue"]:
                    discover_result = self.tool_adapter.call_tool("discover", {
                        "query": ability,
                        "resource_type": "tool"
                    })
                    
                    if discover_result.get("status") == "success":
                        tools = discover_result.get("data", {}).get("tools", [])
                        for tool in tools:
                            tool_name = tool.get("name")
                            if tool_name and tool_name not in [t["function"]["name"] for t in core_tools]:
                                if tool_name in self.tool_adapter.tools:
                                    tool_info = self.tool_adapter.tools[tool_name]
                                    core_tools.append({
                                        "type": "function",
                                        "function": {
                                            "name": tool_name,
                                            "description": tool_info.get("description", ""),
                                            "parameters": tool_info.get("parameters", {})
                                        }
                                    })
                                    
                                    if tool_name.startswith("skill_"):
                                        skill_name = tool_name[6:]
                                        if not self.conversation.has_injected_skill(skill_name):
                                            self._inject_skill_document(skill_name)
        
        return core_tools

    def _execute_step_with_tools(
        self, 
        current_step: Dict, 
        tools: List[Dict], 
        task_tree: Dict,
        step_index: int = 1,
        previous_results: str = ""
    ) -> dict:
        """
        执行需要工具的步骤
        
        Args:
            current_step: 当前步骤
            tools: 工具列表
            task_tree: 任务树
            step_index: 当前步骤序号（从1开始）
            previous_results: 前置结果摘要
        
        Returns:
            执行结果字典，包含 success, content, prompt_tokens, completion_tokens 等
        """
        step_desc = current_step.get("step_desc", "")
        step_id = current_step.get("step_id", "unknown")
        total_steps = task_tree.get("total_steps", 0)
        task_goal = task_tree.get("task_goal", "")
        
        # 前置结果为空时显示引导语
        previous_results_display = previous_results if previous_results else ""
        
        step_prompt = f"""【总体目标】{task_goal}
【当前步骤】{step_id}（第{step_index}/{total_steps}步）
【本步任务】{step_desc}

⚠️ 重要规则：
1. 你只需要执行【本步任务】，不要执行后续步骤
2. 当本步任务完成后，在回答末尾添加 [STEP_DONE] 标记
3. 如果任务无法完成或遇到错误，说明原因并添加 [STEP_FAILED] 标记
5. 输出的内容必须有值，否则系统会崩溃

【前置结果】{previous_results_display}"""
        
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}📍 开始执行步骤: {step_id}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}📝 步骤描述: {step_desc[:100]}{'...' if len(step_desc) > 100 else ''}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
        
        self.conversation.add_message(role="user", content=step_prompt)
        
        current_tool_calls = 0
        max_step_tool_calls = self.max_tool_calls
        counter = TokenCounter()
        has_called_tool = False
        
        while current_tool_calls < max_step_tool_calls:
            current_tool_calls += 1
            
            try:
                messages = self.conversation.get_messages()
                logger.info(f"{Fore.CYAN}[步骤执行] 第 {current_tool_calls} 轮, 消息数: {len(messages) if messages else 0}{Style.RESET_ALL}")
                logger.debug(f"[步骤执行] 工具数: {len(tools) if tools else 0}")
                
                print(f"\n{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}")
                print(f"{Fore.MAGENTA}📤 [{step_id}] 请求消息:{Style.RESET_ALL}")
                print(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}")
                print(messages)
                print(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}\n")
                
                response = self.llm_client.chat_completion(
                    messages=messages,
                    tools=tools,
                    stream=False
                )
                
                counter.add_usage(response)
                
                choice = response.choices[0]
                message = choice.message
                
                reasoning_content = _extract_reasoning_content(message)
                if reasoning_content:
                    print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
                    print(f"{Fore.CYAN}🧠 [{step_id}] 思考过程:{Style.RESET_ALL}")
                    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
                    print(reasoning_content)
                    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
                
                if not self._process_tool_calls(message):
                    required_abilities = current_step.get("required_abilities", [])
                    needs_tool = "llm_response" not in required_abilities
                    content = message.content or ""
                    
                    if "[STEP_FAILED]" in content:
                        final_content = content.replace("[STEP_FAILED]", "").strip()
                        logger.warning(f"{Fore.YELLOW}[步骤执行] 模型报告任务失败{Style.RESET_ALL}")
                        return {
                            "success": False,
                            "error": final_content or "任务执行失败",
                            "content": final_content,
                            "prompt_tokens": counter.total_prompt_tokens,
                            "completion_tokens": counter.total_completion_tokens
                        }
                    
                    if "[STEP_DONE]" in content:
                        final_content = content.replace("[STEP_DONE]", "").strip()
                        self.conversation.add_message(role="assistant", content=content)
                        logger.info(f"{Fore.GREEN}[步骤执行] 模型报告任务完成{Style.RESET_ALL}")
                        print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
                        print(f"{Fore.GREEN}🤖 [{step_id}] 步骤回答:{Style.RESET_ALL}")
                        print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
                        print(final_content)
                        print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}\n")
                        return {
                            "success": True,
                            "content": final_content,
                            "tool_name": "",
                            "arguments": {},
                            "result": {"content": final_content},
                            "prompt_tokens": counter.total_prompt_tokens,
                            "completion_tokens": counter.total_completion_tokens
                        }
                    
                    if needs_tool:
                        if not has_called_tool:
                            warning_msg = "⚠ 当前步骤需要工具调用，请使用工具调用来完成任务，而不是用文字描述。完成后在回答末尾添加 [STEP_DONE] 标记。"
                            logger.warning(f"{Fore.YELLOW}[步骤执行] 需要工具但未调用，要求模型调用工具{Style.RESET_ALL}")
                        else:
                            warning_msg = "⚠ 如果任务已完成请在回答末尾添加 [STEP_DONE] 标记，否则请继续调用工具完成任务。"
                            logger.warning(f"{Fore.YELLOW}[步骤执行] 已调用过工具但未标记完成，询问是否继续{Style.RESET_ALL}")
                        
                        self.conversation.add_message(role="assistant", content=content or reasoning_content or "")
                        self.conversation.add_message(role="user", content=warning_msg)
                        continue
                    
                    self.conversation.add_message(role="assistant", content=content)
                    
                    final_content = content
                    if not final_content and reasoning_content:
                        final_content = reasoning_content
                        logger.info(f"[步骤执行] content为空，使用思考内容作为兜底")
                    
                    print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
                    print(f"{Fore.GREEN}🤖 [{step_id}] 步骤回答:{Style.RESET_ALL}")
                    print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
                    print(final_content)
                    print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}\n")
                    
                    return {
                        "success": True,
                        "content": final_content,
                        "tool_name": "",
                        "arguments": {},
                        "result": {"content": final_content},
                        "prompt_tokens": counter.total_prompt_tokens,
                        "completion_tokens": counter.total_completion_tokens
                    }
                
                has_called_tool = True
                    
            except Exception as e:
                logger.error(f"{Fore.RED}[步骤执行] 工具调用失败: {e}{Style.RESET_ALL}")
                return {
                    "success": False,
                    "error": str(e),
                    "prompt_tokens": counter.total_prompt_tokens,
                    "completion_tokens": counter.total_completion_tokens
                }
        
        return {
            "success": False,
            "error": "达到最大工具调用次数",
            "prompt_tokens": counter.total_prompt_tokens,
            "completion_tokens": counter.total_completion_tokens
        }

    def _get_next_step_desc(self, task_tree: Dict, completed_steps: List[str]) -> str:
        """
        获取下一步骤描述
        
        Args:
            task_tree: 任务树
            completed_steps: 已完成步骤列表
        
        Returns:
            下一步骤描述
        """
        completed_set = set(completed_steps)
        steps = task_tree.get("task_tree", [])
        
        found_current = False
        for step in steps:
            if step["step_id"] in completed_set:
                continue
            if found_current:
                return step.get("step_desc", "")
            found_current = True
        
        return "无"
    
    def _original_chat(self, user_input: str, delegation_depth: Optional[int] = None, images: Optional[List[str]] = None, is_task_step: bool = False) -> dict:
        """
        原始对话方法（不涉及任务拆解）
        
        Args:
            user_input: 用户输入
            delegation_depth: 委托深度（可选）
            images: 图片列表（可选）
            is_task_step: 是否为任务步骤模式（任务拆解模式下的子步骤）
        
        Returns:
            对话结果字典
        """
        if delegation_depth is not None:
            self.delegation_depth = delegation_depth
        
        counter = TokenCounter()
        
        self.conversation.add_message(role="user", content=user_input, images=images)
        
        if not is_task_step and self._auto_save:
            self.conversation.save()
        
        input_summary = user_input[:50] + "..." if len(user_input) > 50 else user_input
        img_info = f", 图片: {len(images)} 张" if images else ""
        logger.info(f"[对话开始] 会话: {self.conversation.session_id}, 输入: {input_summary}{img_info}")
        
        print_conversation_history(self.conversation.get_messages(), max_content_length=88888, print_last_only=True)
        current_tool_calls = 0
        
        tools = self._prepare_tools_with_preprocess(user_input)
   
        logger.info(f"[工具准备] 工具数: {len(tools)}")

        while current_tool_calls < self.max_tool_calls:
            current_tool_calls += 1
            messages = self.conversation.get_messages()
            logger.info(f"{Fore.CYAN}[LLM调用] 第 {current_tool_calls} 轮, 消息数: {len(messages)}{Style.RESET_ALL}")
            
            try:
                response = self.llm_client.chat_completion(
                    messages=messages,
                    tools=tools,
                    stream=False
                )
                
                counter.add_usage(response)
            except Exception as e:
                logger.error(f"[LLM错误] {str(e)}")
                self._clear_skill_state()
                self.conversation.cancel_conversation()
                if not is_task_step and self._auto_save:
                    self.conversation.save()
                
                return counter.build_result(f"大模型调用失败：{str(e)}")

            choice = response.choices[0]
            message = choice.message

            reasoning_content = _extract_reasoning_content(message)
            
            has_tool_calls = hasattr(message, "tool_calls") and message.tool_calls
            
            if has_tool_calls:
                if reasoning_content:
                    logger.debug(f"[思考过程-工具调用] 模型进行了推理思考:")
                    print(f"\n{Fore.MAGENTA}{'='*60}")
                    print(f"🧠 思考过程 (工具调用阶段):")
                    print(f"{'='*60}{Style.RESET_ALL}")
                    print(f"{Fore.YELLOW}{reasoning_content}{Style.RESET_ALL}")
                    print(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}\n")
            else:
                if reasoning_content:
                    logger.debug(f"[思考过程] 模型进行了推理思考:")
                    print(f"\n{Fore.CYAN}{'='*60}")
                    print(f"🧠 思考过程 (最终回答阶段):")
                    print(f"{'='*60}{Style.RESET_ALL}")
                    print(f"{Fore.YELLOW}{reasoning_content}{Style.RESET_ALL}")
                    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")

            if not self._process_tool_calls(message):
                self.conversation.add_message(role="assistant", content=message.content)
                
                print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
                print(f"{Fore.GREEN}🤖 回答:{Style.RESET_ALL}")
                print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
                print(message.content or "message.content=None")
                print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}\n")
                
                response_len = len(message.content) if message.content else 0
                logger.info(f"[对话结束] 会话: {self.conversation.session_id}, 回答长度: {response_len}, 耗时: {counter.elapsed_time:.2f}s")

                self._clear_skill_state()

                if is_task_step:
                    with self.conversation._lock:
                        self.conversation._working_messages.clear()
                    logger.debug(f"[任务步骤] 清理临时工作区，不保存到历史")
                else:
                    self.conversation.finalize_conversation()
                    if self._auto_save:
                        self.conversation.save()

                return counter.build_result(message.content or "")

        self._clear_skill_state()

        self.conversation.cancel_conversation()

        if not is_task_step and self._auto_save:
            self.conversation.save()
        
        return counter.build_result("已达到最大工具调用轮数，无法继续执行")

    def _process_tool_calls(self, message: Any) -> bool:
        """
        处理工具调用
        
        Args:
            message: 大模型返回的消息对象
        
        Returns:
            是否处理了工具调用
        """
        if not hasattr(message, "tool_calls") or not message.tool_calls:
            return False
        
        logger.info(f"{Fore.CYAN}检测到工具调用请求，共 {len(message.tool_calls)} 个工具{Style.RESET_ALL}")
        
        tool_names = [tc.function.name for tc in message.tool_calls if tc.function.name]
        logger.info(f"{Fore.CYAN}工具调用: {tool_names}{Style.RESET_ALL}")

        tool_calls_list: List[Dict[str, Any]] = []
        valid_tool_calls = []
        for tc in message.tool_calls:
            if tc.function.name:
                tool_calls_list.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                })
                valid_tool_calls.append(tc)
            else:
                logger.warning(f"{Fore.YELLOW}跳过无效工具调用: name=None, id={tc.id}{Style.RESET_ALL}")
        
        if not valid_tool_calls:
            logger.warning(f"{Fore.YELLOW}所有工具调用都无效，跳过处理{Style.RESET_ALL}")
            return False
        
        assistant_content = message.content or ""
        self.conversation.add_message(
            role="assistant",
            content=assistant_content,
            tool_calls=tool_calls_list
        )
        logger.info(f"{Fore.CYAN}已将 assistant 消息添加到对话历史，包含 {len(tool_calls_list)} 个工具调用{Style.RESET_ALL}")

        invalid_call_count = 0
        max_invalid_calls = 7

        for idx, tool_call in enumerate(valid_tool_calls, 1):
            tool_name = tool_call.function.name
            logger.info(f"{Fore.YELLOW}[{idx}/{len(valid_tool_calls)}] 正在执行工具: {tool_name}{Style.RESET_ALL}")

            invalid_reason = None
            if not tool_call.function.arguments:
                invalid_reason = "工具参数为空"
            else:
                try:
                    args = json.loads(tool_call.function.arguments)
                    if not args or args == {}:
                        invalid_reason = "工具参数为空对象"
                except json.JSONDecodeError:
                    invalid_reason = f"参数格式错误: {tool_call.function.arguments[:50]}"

            if invalid_reason:
                invalid_call_count += 1
                error_msg = f"无效工具调用（{invalid_reason}）。请检查工具名称和参数是否正确。"
                logger.error(f"{Fore.RED}无效工具调用: {invalid_reason}（第 {invalid_call_count} 次）{Style.RESET_ALL}")
                self.conversation.add_tool_result(tool_call.id, tool_name, error_msg)
                
                if invalid_call_count >= max_invalid_calls:
                    final_error = (
                        f"连续 {max_invalid_calls} 次无效工具调用。"
                        f"可能原因：\n"
                        f"1. 工具名称为空或不存在\n"
                        f"2. 必填参数缺失或格式错误\n"
                        f"3. 当前任务可能无法通过工具完成\n"
                        f"请重新描述您的需求，或尝试简化问题。"
                    )
                    logger.error(f"{Fore.RED}连续 {max_invalid_calls} 次无效工具调用，终止循环{Style.RESET_ALL}")
                    self.conversation.add_tool_result(tool_call.id, tool_name, final_error)
                    return True
                continue

            invalid_call_count = 0

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
        logger.info(f"{Fore.CYAN}所有工具调用完成，继续生成回答...{Style.RESET_ALL}")
        
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

    def chat(self, user_input: str, delegation_depth: Optional[int] = None, images: Optional[List[str]] = None) -> dict:
        """
        非流式对话方法（用于CLI和API调用），支持技能文档动态注入和任务拆解。

        Args:
            user_input: 用户输入
            delegation_depth: 委托深度（覆盖实例级别），用于子代理调用
            images: 图片列表（可选），每项为 URL 或 base64 字符串

        Returns:
            dict: 包含 content, elapsed_time, total_prompt_tokens, total_completion_tokens
        """
        with TokenCounter() as counter:
            if delegation_depth is not None:
                self.delegation_depth = delegation_depth
            
            if not self.task_decomposer or not self.task_tree_manager or not self.heartbeat_manager:
                logger.info(f"{Fore.YELLOW}[任务拆解] 模块未初始化，使用普通对话模式{Style.RESET_ALL}")
                result = self._original_chat(user_input, None, images)
                counter.add_tokens(
                    result.get("total_prompt_tokens", 0),
                    result.get("total_completion_tokens", 0)
                )
                
                context_window = self.llm_client.get_context_window()
                history_tokens = self.llm_client.count_tokens(self.conversation.get_messages())
                context_usage_percent = (history_tokens / context_window * 100) if context_window > 0 else 0
                
                result["context_window"] = context_window
                result["context_usage_percent"] = context_usage_percent
                
                return result
            
            with self.conversation._lock:
                self.conversation.history.append({"role": "user", "content": user_input})
            if self._auto_save:
                self.conversation.save()
            logger.info(f"[任务拆解] 用户消息已保存到历史")
            
            pending_task = self._check_pending_task()
            
            ability_tags = []
            if self.memory_system:
                ability_tags = self.memory_system.get_all_ability_tags() or []
            
            if not ability_tags:
                ability_tags = ["llm_response", "文件读取", "文件写入", "命令执行", "网络搜索"]
            
            try:
                task_tree = self.task_decomposer.analyze_and_decompose(
                    user_task=user_input,
                    ability_tags=ability_tags,
                    pending_task=pending_task
                )
                
                counter.add_tokens(
                    task_tree.get("prompt_tokens", 0),
                    task_tree.get("completion_tokens", 0)
                )
                
                task_type = task_tree.get("task_type", "new_task")
                logger.info(f"{Fore.CYAN}[任务分析] task_type: {task_type}{Style.RESET_ALL}")
                
                result = self._execute_by_task_type(task_tree, user_input, counter)
                
                context_window = self.llm_client.get_context_window()
                history_tokens = self.llm_client.count_tokens(self.conversation.get_messages())
                context_usage_percent = (history_tokens / context_window * 100) if context_window > 0 else 0
                
                result["context_window"] = context_window
                result["context_usage_percent"] = context_usage_percent
                
                return result
                
            except Exception as e:
                logger.error(f"{Fore.RED}[任务分析] 失败: {e}{Style.RESET_ALL}")
                return counter.build_result(f"任务分析失败: {str(e)}")
