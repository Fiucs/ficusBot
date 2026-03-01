#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :agent_config.py
# @Time      :2026/03/01
# @Author    :Ficus

"""
Agent 配置数据类

该模块定义了 Agent 的配置结构，支持从配置文件加载和运行时修改。
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class AgentConfig:
    """
    Agent 配置数据类
    
    Attributes:
        agent_id: Agent 唯一标识符
        description: Agent 描述
        model: 使用的模型（格式：厂商/模型别名）
        llm_preset: LLM 参数预设名称（引用 llm.agent_presets）
        tools: 可用工具列表（支持通配符 *）
        skills: 可用技能列表（支持通配符 *）
        sub_agents: 可委托的子代理列表
        system_prompt: 自定义系统提示词
        max_tool_calls: 最大工具调用次数
        extra: 额外配置参数
    """
    agent_id: str
    description: str = ""
    model: str = ""
    llm_preset: Optional[str] = None
    tools: List[str] = field(default_factory=lambda: ["*"])
    skills: List[str] = field(default_factory=lambda: ["*"])
    sub_agents: List[str] = field(default_factory=list)
    system_prompt: Optional[str] = None
    max_tool_calls: int = 8
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, agent_id: str, config: Dict[str, Any]) -> "AgentConfig":
        """
        从字典创建 AgentConfig 实例
        
        Args:
            agent_id: Agent 唯一标识符
            config: 配置字典
            
        Returns:
            AgentConfig 实例
        """
        return cls(
            agent_id=agent_id,
            description=config.get("description", ""),
            model=config.get("model", ""),
            llm_preset=config.get("llm_preset"),
            tools=config.get("tools", ["*"]),
            skills=config.get("skills", ["*"]),
            sub_agents=config.get("sub_agents", []),
            system_prompt=config.get("system_prompt"),
            max_tool_calls=config.get("max_tool_calls", 8),
            extra=config.get("extra", {})
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式
        
        Returns:
            配置字典
        """
        return {
            "agent_id": self.agent_id,
            "description": self.description,
            "model": self.model,
            "llm_preset": self.llm_preset,
            "tools": self.tools,
            "skills": self.skills,
            "sub_agents": self.sub_agents,
            "system_prompt": self.system_prompt,
            "max_tool_calls": self.max_tool_calls,
            "extra": self.extra
        }
    
    def get_llm_params(self) -> Dict[str, Any]:
        """
        获取合并后的 LLM 参数
        
        合并优先级：llm_preset > llm.global
        
        Returns:
            LLM 参数字典
        """
        from agent.config.configloader import GLOBAL_CONFIG
        
        params = {}
        
        global_params = GLOBAL_CONFIG.get("llm.global", {})
        params.update(global_params)
        
        if self.llm_preset:
            presets = GLOBAL_CONFIG.get("llm.agent_presets", {})
            preset_params = presets.get(self.llm_preset, {})
            params.update(preset_params)
        
        return params
