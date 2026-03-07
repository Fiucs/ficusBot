#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :agent_config.py
# @Time      :2026/03/01
# @Author    :Ficus

"""
Agent 配置数据类

该模块定义了 Agent 的配置结构，支持从配置文件加载和运行时修改。
支持 Agent 级别配置覆盖全局配置。
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
        workspace_root: Agent 专属工作目录（None 使用全局配置）
        file_allow_list: Agent 专属文件白名单（None 使用全局配置）
        shell_cmd_whitelist: Agent 专属命令白名单（None 使用全局配置）
        shell_cmd_deny_list: Agent 专属命令黑名单（追加到全局黑名单）
        shell_path_whitelist: Agent 专属路径白名单（NONE 使用全局配置）
        shell_path_deny_list: Agent 专属路径黑名单（追加到全局黑名单）
        exec_timeout: Agent 专属执行超时时间（None 使用全局配置）
        conversation_config: Agent 专属对话配置（None 使用全局配置）
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
    workspace_root: Optional[str] = None
    file_allow_list: Optional[List[str]] = None
    shell_cmd_whitelist: Optional[List[str]] = None
    shell_cmd_deny_list: Optional[List[str]] = None
    shell_path_whitelist: Optional[List[str]] = None
    shell_path_deny_list: Optional[List[str]] = None
    exec_timeout: Optional[int] = None
    conversation_config: Optional[Dict[str, Any]] = None

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
            extra=config.get("extra", {}),
            workspace_root=config.get("workspace_root"),
            file_allow_list=config.get("file_allow_list"),
            shell_cmd_whitelist=config.get("shell_cmd_whitelist"),
            shell_cmd_deny_list=config.get("shell_cmd_deny_list"),
            shell_path_whitelist=config.get("shell_path_whitelist"),
            shell_path_deny_list=config.get("shell_path_deny_list"),
            exec_timeout=config.get("exec_timeout"),
            conversation_config=config.get("conversation")
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
            "extra": self.extra,
            "workspace_root": self.workspace_root,
            "file_allow_list": self.file_allow_list,
            "shell_cmd_whitelist": self.shell_cmd_whitelist,
            "shell_cmd_deny_list": self.shell_cmd_deny_list,
            "shell_path_whitelist": self.shell_path_whitelist,
            "shell_path_deny_list": self.shell_path_deny_list,
            "exec_timeout": self.exec_timeout,
            "conversation": self.conversation_config
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
    
    def get_workspace_root(self) -> str:
        """
        获取工作目录（Agent 级别覆盖全局）
        
        Returns:
            工作目录路径
        """
        from agent.config.configloader import GLOBAL_CONFIG
        if self.workspace_root:
            return self.workspace_root
        return GLOBAL_CONFIG.get("workspace_root", "./workspace")
    
    def get_file_allow_list(self) -> List[str]:
        """
        获取文件白名单（Agent 级别覆盖全局）
        
        Returns:
            文件白名单列表
        """
        from agent.config.configloader import GLOBAL_CONFIG
        if self.file_allow_list is not None:
            return self.file_allow_list
        return GLOBAL_CONFIG.get("file_allow_list", [])
    
    def get_shell_cmd_whitelist(self) -> List[str]:
        """
        获取命令白名单（Agent 级别覆盖全局）
        
        Returns:
            命令白名单列表
        """
        from agent.config.configloader import GLOBAL_CONFIG
        if self.shell_cmd_whitelist is not None:
            return self.shell_cmd_whitelist
        return GLOBAL_CONFIG.get("shell_cmd_whitelist", [])
    
    def get_shell_cmd_deny_list(self) -> List[str]:
        """
        获取命令黑名单（Agent 级别追加到全局）
        
        Returns:
            合并后的命令黑名单列表
        """
        from agent.config.configloader import GLOBAL_CONFIG
        global_deny = GLOBAL_CONFIG.get("shell_cmd_deny_list", [])
        if self.shell_cmd_deny_list:
            return global_deny + self.shell_cmd_deny_list
        return global_deny
    
    def get_shell_path_whitelist(self) -> List[str]:
        """
        获取路径白名单（Agent 级别覆盖全局）
        
        Returns:
            路径白名单列表
        """
        from agent.config.configloader import GLOBAL_CONFIG
        if self.shell_path_whitelist is not None:
            return self.shell_path_whitelist
        return GLOBAL_CONFIG.get("shell_path_whitelist", [])
    
    def get_shell_path_deny_list(self) -> List[str]:
        """
        获取路径黑名单（Agent 级别追加到全局）
        
        Returns:
            合并后的路径黑名单列表
        """
        from agent.config.configloader import GLOBAL_CONFIG
        global_deny = GLOBAL_CONFIG.get("shell_path_deny_list", [])
        if self.shell_path_deny_list:
            return global_deny + self.shell_path_deny_list
        return global_deny
    
    def get_exec_timeout(self) -> int:
        """
        获取执行超时时间（Agent 级别覆盖全局）
        
        Returns:
            超时时间（秒）
        """
        from agent.config.configloader import GLOBAL_CONFIG
        if self.exec_timeout is not None:
            return self.exec_timeout
        return GLOBAL_CONFIG.get("exec_timeout", 60)
    
    def get_conversation_config(self) -> Dict[str, Any]:
        """
        获取对话配置（Agent 级别覆盖全局）
        
        Returns:
            对话配置字典
        """
        from agent.config.configloader import GLOBAL_CONFIG
        global_conv = GLOBAL_CONFIG.get("conversation", {})
        if self.conversation_config:
            merged = global_conv.copy()
            for k, v in self.conversation_config.items():
                if v is not None:
                    merged[k] = v
            return merged
        return global_conv
