#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :subagent_tool.py
# @Time      :2026/03/01
# @Author    :Ficus

"""
子代理工具

该模块将子代理封装为可调用的工具，允许主 Agent 委托任务给子代理。
"""
import asyncio
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from agent.config.configloader import GLOBAL_CONFIG
from loguru import logger
from colorama import Fore, Style

if TYPE_CHECKING:
    from agent.config.agent_config import AgentConfig


class SubAgentTool:
    """
    子代理工具
    
    将子代理封装为工具，主 Agent 可通过工具调用方式委托任务。
    
    工具命名格式: agent.<agent_id>.delegate
    例如: agent.coder.delegate
    
    Attributes:
        delegation_depth: 当前委托深度
        max_delegation_depth: 最大委托深度
        timeout: 子代理执行超时时间
        pass_context: 是否传递上下文
        return_summary: 是否返回摘要
    """
    
    def __init__(self, delegation_depth: int = 0):
        """
        初始化子代理工具
        
        Args:
            delegation_depth: 当前委托深度（用于防止无限递归）
        """
        self.delegation_depth = delegation_depth
        self._load_config()
    
    def _load_config(self):
        """
        加载子代理配置
        """
        config = GLOBAL_CONFIG.get("sub_agent_config", {})
        self.max_delegation_depth = config.get("max_delegation_depth", 3)
        self.timeout = config.get("timeout", 120)
        self.pass_context = config.get("pass_context", True)
        self.return_summary = config.get("return_summary", True)
    
    def get_tool_definitions(self, available_sub_agents: List[str]) -> List[Dict]:
        """
        获取子代理工具定义（OpenAI Function Calling 格式）
        
        Args:
            available_sub_agents: 可用的子代理 ID 列表
            
        Returns:
            工具定义列表
        """
        from agent.registry import AGENT_REGISTRY
        
        tools = []
        
        for agent_id in available_sub_agents:
            config = AGENT_REGISTRY.get_config(agent_id)
            if not config:
                continue
            
            tool = {
                "type": "function",
                "function": {
                    "name": f"agent.{agent_id}.delegate",
                    "description": f"委托任务给 {agent_id} Agent。{config.description}",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task": {
                                "type": "string",
                                "description": "要委托的任务描述"
                            },
                            "context": {
                                "type": "string",
                                "description": "任务相关的上下文信息（可选）"
                            },
                            "expect_output": {
                                "type": "string",
                                "description": "期望的输出格式或内容（可选）"
                            }
                        },
                        "required": ["task"]
                    }
                }
            }
            tools.append(tool)
        
        return tools
    
    def call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行子代理调用（同步版本）
        
        Args:
            tool_name: 工具名称，格式: agent.<agent_id>.delegate
            arguments: 调用参数
            
        Returns:
            子代理执行结果字典
        """
        from agent.registry import AGENT_REGISTRY
        
        if self.delegation_depth >= self.max_delegation_depth:
            error_msg = f"错误：已达到最大委托深度 ({self.max_delegation_depth})，无法继续委托"
            logger.warning(f"{Fore.YELLOW}[SubAgentTool] {error_msg}{Style.RESET_ALL}")
            return {"status": "error", "message": error_msg}
        
        parts = tool_name.split(".")
        if len(parts) < 3 or parts[0] != "agent":
            error_msg = f"错误：无效的工具名称格式: {tool_name}"
            logger.error(f"{Fore.RED}[SubAgentTool] {error_msg}{Style.RESET_ALL}")
            return {"status": "error", "message": error_msg}
        
        agent_id = parts[1]
        task = arguments.get("task", "")
        context = arguments.get("context", "")
        expect_output = arguments.get("expect_output", "")
        
        if not task:
            return {"status": "error", "message": "缺少必需参数: task"}
        
        try:
            sub_agent = AGENT_REGISTRY.get_agent(agent_id)
            
            prompt = self._build_prompt(task, context, expect_output)
            
            logger.info(f"{Fore.CYAN}[SubAgentTool] 委托任务给 {agent_id} Agent (深度: {self.delegation_depth + 1}){Style.RESET_ALL}")
            
            result = sub_agent.chat(
                user_input=prompt,
                delegation_depth=self.delegation_depth + 1
            )
            
            content = result.get("content", "")
            
            if result.get("status") == "error" or "大模型调用失败" in content or "API" in content and "error" in content.lower():
                error_msg = f"子代理 {agent_id} 执行失败: {content}"
                logger.error(f"{Fore.RED}[SubAgentTool] {error_msg}{Style.RESET_ALL}")
                return {
                    "status": "error",
                    "message": error_msg,
                    "agent_id": agent_id,
                    "elapsed_time": result.get("elapsed_time", 0)
                }
            
            if self.return_summary and len(content) > 2000:
                content = content[:2000] + "\n...[内容已截断]"
            
            return {
                "status": "success",
                "message": f"子代理 {agent_id} 执行完成",
                "result": content,
                "agent_id": agent_id,
                "elapsed_time": result.get("elapsed_time", 0)
            }
            
        except ValueError as e:
            error_msg = f"子代理 {agent_id} 不存在: {str(e)}"
            logger.error(f"{Fore.RED}[SubAgentTool] {error_msg}{Style.RESET_ALL}")
            return {"status": "error", "message": error_msg}
        except Exception as e:
            error_msg = f"子代理 {agent_id} 执行失败: {str(e)}"
            logger.error(f"{Fore.RED}[SubAgentTool] {error_msg}{Style.RESET_ALL}")
            return {"status": "error", "message": error_msg}
    
    def _build_prompt(self, task: str, context: str, expect_output: str) -> str:
        """
        构建发送给子代理的提示
        
        Args:
            task: 任务描述
            context: 上下文信息
            expect_output: 期望输出
            
        Returns:
            完整提示
        """
        prompt_parts = [f"[委托任务]\n{task}"]
        
        if context:
            prompt_parts.append(f"\n[上下文信息]\n{context}")
        
        if expect_output:
            prompt_parts.append(f"\n[期望输出]\n{expect_output}")
        
        prompt_parts.append("\n\n请完成上述任务并返回结果。")
        
        return "\n".join(prompt_parts)


def get_subagent_tools_for_agent(agent_config: "AgentConfig", delegation_depth: int = 0) -> List[Dict]:
    """
    获取指定 Agent 可用的子代理工具定义
    
    Args:
        agent_config: Agent 配置
        delegation_depth: 当前委托深度
        
    Returns:
        工具定义列表
    """
    max_depth = GLOBAL_CONFIG.get("sub_agent_config.max_delegation_depth", 3)
    
    if delegation_depth >= max_depth:
        return []
    
    sub_agent_config = GLOBAL_CONFIG.get("sub_agent_config", {})
    enabled = sub_agent_config.get("enabled", True)
    
    if not enabled:
        return []
    
    tool = SubAgentTool(delegation_depth)
    return tool.get_tool_definitions(agent_config.sub_agents)
