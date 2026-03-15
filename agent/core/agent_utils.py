#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :agent_utils.py
# @Time      :2026/03/12
# @Author    :Ficus

"""
Agent 工具函数模块

该模块包含 Agent 使用的工具函数，包括消息处理和工具管理相关功能。
"""
import json
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from colorama import Fore, Style
from loguru import logger

from agent.config.configloader import GLOBAL_CONFIG
from agent.utils import words_utils

if TYPE_CHECKING:
    from agent.core.agent import Agent


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


def _extract_and_remove_think_tags(content: str) -> tuple[Optional[str], str]:
    """
    从 content 中提取 <think> 标签内容，并返回清理后的 content。

    用于处理某些模型（如 Qwen3）将思考内容放在 <think>...</think> 标签中的情况。

    Args:
        content: 原始内容字符串

    Returns:
        tuple: (思考内容, 清理后的内容)
        - 思考内容: 提取的 <think> 标签内内容，无则返回 None
        - 清理后的内容: 移除了 <think> 标签后的内容

    Example:
        >>> content = "<think>这是思考</think>这是回答"
        >>> think, clean = _extract_and_remove_think_tags(content)
        >>> print(think)  # "这是思考"
        >>> print(clean)  # "这是回答"
    """
    import re

    if not content:
        return None, content

    # 匹配 <think> 标签内容（支持多行，非贪婪匹配）
    pattern = r'<think>(.*?)</think>'
    matches = re.findall(pattern, content, re.DOTALL)

    if matches:
        # 提取所有 think 内容并合并
        think_content = '\n'.join(match.strip() for match in matches)
        # 移除所有 <think>...</think> 标签
        clean_content = re.sub(pattern, '', content, flags=re.DOTALL).strip()
        return think_content, clean_content

    return None, content


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


class ToolManager:
    """
    工具管理器，负责工具的准备、处理和调用管理。
    
    功能说明:
        - 获取核心工具列表
        - 预处理用户输入，预测需要的工具
        - 准备工具列表（核心工具 + 预测工具）
        - 处理工具调用
        - 注入技能文档
    
    核心方法:
        - get_core_tool_names: 获取核心工具名称列表
        - get_core_tools: 获取核心工具定义列表
        - preprocess_user_input: 预处理用户输入，预测工具
        - prepare_tools_with_preprocess: 准备完整工具列表
        - process_tool_calls: 处理工具调用
        - inject_skill_document: 注入技能文档
    
    配置项:
        - agent: Agent 实例引用
    """
    
    def __init__(self, agent: "Agent"):
        """
        初始化工具管理器。
        
        Args:
            agent: Agent 实例
        """
        self.agent = agent
    
    def get_core_tool_names(self) -> List[str]:
        """
        获取核心工具名称列表（始终加载）
        
        从 tool_index.json 中读取 category="core" 的工具，结果会被缓存以避免重复读取文件。
        如果 memory_system 未初始化，则使用默认的核心工具列表。
        
        Returns:
            核心工具名称列表
        """
        default_core_tools = []
        
        # 检查缓存是否存在且有效
        if hasattr(self.agent, '_core_tool_names_cache') and self.agent._core_tool_names_cache is not None:
            return self.agent._core_tool_names_cache
        
        if not self.agent.memory_system:
            return default_core_tools
        
        try:
            # 通过 tool_store 读取工具索引（MemorySystem 重构后 _read_tool_index 在 tool_store 中）
            data = self.agent.memory_system.tool_store._read_tool_index()
            tools = data.get("tools", [])
            core_names = [t["name"] for t in tools if t.get("category") == "core" and t.get("enabled", True)]
            
            # 缓存结果
            self.agent._core_tool_names_cache = core_names if core_names else default_core_tools
            return self.agent._core_tool_names_cache
        except Exception as e:
            logger.warning(f"读取核心工具列表失败，使用默认值: {e}")
            return default_core_tools
    
    def get_core_tools(self) -> List[Dict[str, Any]]:
        """
        获取核心工具列表（始终加载）
        
        Returns:
            工具定义列表
        """
        core_names = set(self.get_core_tool_names())
        logger.debug(f"[_get_core_tools] 核心工具名称: {core_names}")
        logger.debug(f"[_get_core_tools] tool_adapter.tools 中的工具: {list(self.agent.tool_adapter.tools.keys())}")
        core_tools = []
        
        for name in core_names:
            if name in self.agent.tool_adapter.tools:
                tool_info = self.agent.tool_adapter.tools[name]
                core_tools.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool_info["description"],
                        "parameters": tool_info["parameters"]
                    }
                })
        
        return core_tools
    
    def preprocess_user_input(self, user_input: Any) -> List[str]:
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
        logger.info(f"[预处理] 开始预处理, memory_system={self.agent.memory_system is not None}")
        
        if not self.agent.memory_system:
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
            
            tools = self.agent.tool_adapter._run_async(
                self.agent.memory_system.search_tools_batch(queries, top_k=top_k, distance_threshold=distance_threshold)
            )
            
            logger.debug(f"[预处理] 搜索返回 {len(tools)} 个工具")
            
            registered = []
            seen_names = set()
            for tool_def in tools:
                func_def = tool_def.get("function", tool_def)
                tool_name = func_def.get("name", "")
                if tool_name and tool_name not in seen_names:
                    if self.agent.tool_adapter._register_skill_tool(tool_name, func_def):
                        registered.append(tool_name)
                        seen_names.add(tool_name)
                        logger.info(f"[预处理] 预测加载工具: {tool_name}")
            
            return registered
        except Exception as e:
            logger.warning(f"[预处理] 工具预测失败: {e}")
            return []
    
    def prepare_tools_with_preprocess(self, user_input: str) -> List[Dict[str, Any]]:
        """
        准备工具列表（核心工具 + 预测工具）
        
        Args:
            user_input: 用户输入
        
        Returns:
            工具定义列表
        """
        core_tools = self.get_core_tools()
        core_names = {t["function"]["name"] for t in core_tools}
        
        predicted_names = self.preprocess_user_input(user_input)
        
        predicted_tools = []
        for name in predicted_names:
            if name not in core_names and name in self.agent.tool_adapter.tools:
                tool_info = self.agent.tool_adapter.tools[name]
                predicted_tools.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool_info["description"],
                        "parameters": tool_info["parameters"]
                    }
                })
        
        all_tools = core_tools + predicted_tools
        
        if self.agent.agent_config and self.agent.agent_config.sub_agents:
            from agent.tool.subagent_tool import get_subagent_tools_for_agent
            subagent_tools = get_subagent_tools_for_agent(
                self.agent.agent_config, 
                self.agent.delegation_depth
            )
            all_tools.extend(subagent_tools)
        
        logger.info(f"[工具准备] 核心={len(core_tools)}, 预测={len(predicted_tools)}, 总计={len(all_tools)}")
        
        return all_tools
    
    def inject_skill_document(self, skill_name: str) -> bool:
        """
        从 SkillLoader 获取完整技能文档并注入到 system prompt。

        Args:
            skill_name: 技能名称

        Returns:
            bool: 注入是否成功
        """
        try:
            skill_info = self.agent.skill_loader.get_skill_info(skill_name)
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

            success = self.agent.conversation.inject_skill_document(skill_name, skill_doc)

            if success:
                logger.info(f"{Fore.GREEN}✓ 技能 '{skill_name}' 文档已注入 system prompt{Style.RESET_ALL}")
            else:
                logger.warning(f"{Fore.YELLOW}⚠ 技能 '{skill_name}' 文档注入失败{Style.RESET_ALL}")

            return success

        except Exception as e:
            logger.error(f"{Fore.RED}技能文档注入过程出错: {str(e)}{Style.RESET_ALL}")
            return False
