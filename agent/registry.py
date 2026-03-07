#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :registry.py
# @Time      :2026/03/01
# @Author    :Ficus

"""
Agent 注册中心

该模块提供 Agent 实例的创建、管理和获取功能，支持多 Agent 架构。
"""
import threading
from typing import Dict, Optional, List, TYPE_CHECKING
from agent.config.agent_config import AgentConfig
from agent.config.configloader import GLOBAL_CONFIG
from loguru import logger
from colorama import Fore, Style

if TYPE_CHECKING:
    from agent.core.agent import Agent


class AgentRegistry:
    """
    Agent 注册中心
    
    负责管理所有 Agent 实例的创建、获取和销毁。
    采用懒加载模式，仅在首次访问时创建 Agent 实例。
    
    Attributes:
        _agents: Agent 实例缓存字典
        _configs: Agent 配置字典
        _lock: 线程锁，保证线程安全
        _default_agent_id: 默认 Agent ID
    """
    
    _instance: Optional["AgentRegistry"] = None
    _lock = threading.RLock()
    
    def __new__(cls) -> "AgentRegistry":
        """
        单例模式：确保全局只有一个注册中心实例
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """
        初始化注册中心
        """
        if self._initialized:
            return
        self._agents: Dict[str, "Agent"] = {}
        self._configs: Dict[str, AgentConfig] = {}
        self._default_agent_id: str = "default"
        self._initialized = True
        self._load_configs()
    
    def _load_configs(self):
        """
        从配置文件加载所有 Agent 配置
        """
        agents_config = GLOBAL_CONFIG.get("agents", {})
        
        if not agents_config:
            agents_config = {
                "default": {
                    "description": "默认通用Agent，处理一般性任务",
                    "model": GLOBAL_CONFIG.get("llm.default_model", ""),
                    "tools": ["*"],
                    "skills": ["*"],
                    "sub_agents": [],
                    "system_prompt": None,
                    "max_tool_calls": GLOBAL_CONFIG.get("llm.max_tool_calls", 8)
                }
            }
        
        for agent_id, config in agents_config.items():
            self._configs[agent_id] = AgentConfig.from_dict(agent_id, config)
        
        logger.info(f"{Fore.CYAN}[AgentRegistry] 已加载 {len(self._configs)} 个 Agent 配置{Style.RESET_ALL}")
    
    def get_agent(self, agent_id: Optional[str] = None) -> "Agent":
        """
        获取 Agent 实例（懒加载）
        
        Args:
            agent_id: Agent ID，为空则返回默认 Agent
            
        Returns:
            Agent 实例
            
        Raises:
            ValueError: Agent ID 不存在
        """
        if agent_id is None:
            agent_id = self._default_agent_id
        
        if agent_id not in self._configs:
            raise ValueError(f"Agent '{agent_id}' not found in registry")
        
        if agent_id not in self._agents:
            with self._lock:
                if agent_id not in self._agents:
                    self._agents[agent_id] = self._create_agent(agent_id)
        
        return self._agents[agent_id]
    
    def _create_agent(self, agent_id: str) -> "Agent":
        """
        创建 Agent 实例
        
        Args:
            agent_id: Agent ID
            
        Returns:
            新创建的 Agent 实例
        """
        from agent.core.agent import Agent
        config = self._configs[agent_id]
        logger.info(f"{Fore.GREEN}[AgentRegistry] 创建 Agent 实例: {agent_id}{Style.RESET_ALL}")
        return Agent(agent_config=config)
    
    def list_agents(self) -> List[str]:
        """
        列出所有已注册的 Agent ID
        
        Returns:
            Agent ID 列表
        """
        return list(self._configs.keys())
    
    def get_config(self, agent_id: str) -> Optional[AgentConfig]:
        """
        获取 Agent 配置
        
        Args:
            agent_id: Agent ID
            
        Returns:
            AgentConfig 实例
        """
        return self._configs.get(agent_id)
    
    def register_agent(self, config: AgentConfig) -> str:
        """
        动态注册新 Agent
        
        Args:
            config: Agent 配置
            
        Returns:
            Agent ID
        """
        self._configs[config.agent_id] = config
        logger.info(f"{Fore.GREEN}[AgentRegistry] 注册新 Agent: {config.agent_id}{Style.RESET_ALL}")
        return config.agent_id
    
    def unregister_agent(self, agent_id: str) -> bool:
        """
        注销 Agent
        
        Args:
            agent_id: Agent ID
            
        Returns:
            是否成功注销
        """
        if agent_id in self._agents:
            del self._agents[agent_id]
        if agent_id in self._configs:
            del self._configs[agent_id]
            logger.info(f"{Fore.YELLOW}[AgentRegistry] 注销 Agent: {agent_id}{Style.RESET_ALL}")
            return True
        return False
    
    def set_default(self, agent_id: str):
        """
        设置默认 Agent
        
        Args:
            agent_id: Agent ID
        """
        if agent_id in self._configs:
            self._default_agent_id = agent_id
            logger.info(f"{Fore.CYAN}[AgentRegistry] 设置默认 Agent: {agent_id}{Style.RESET_ALL}")
    
    def reload(self):
        """
        重载所有配置和 Agent 实例
        """
        with self._lock:
            self._agents.clear()
            self._configs.clear()
            self._load_configs()
            logger.info(f"{Fore.GREEN}[AgentRegistry] 配置已重载{Style.RESET_ALL}")
    
    def preload_agents(self, agent_ids: Optional[List[str]] = None) -> Dict[str, "Agent"]:
        """
        预加载指定的 Agent 实例
        
        Args:
            agent_ids: 要预加载的 Agent ID 列表，为 None 时加载所有配置的 Agent
            
        Returns:
            已加载的 Agent 实例字典 {agent_id: Agent}
        """
        if agent_ids is None:
            agent_ids = self.list_agents()
        
        loaded = {}
        for agent_id in agent_ids:
            if agent_id in self._configs:
                try:
                    loaded[agent_id] = self.get_agent(agent_id)
                except Exception as e:
                    logger.error(f"{Fore.RED}[AgentRegistry] 预加载 Agent {agent_id} 失败: {e}{Style.RESET_ALL}")
        
        logger.info(f"{Fore.GREEN}[AgentRegistry] 预加载完成: {list(loaded.keys())}{Style.RESET_ALL}")
        return loaded
    
    def start_all_agents(self) -> Dict[str, "Agent"]:
        """
        启动所有配置的 Agent 实例
        
        Returns:
            所有 Agent 实例字典 {agent_id: Agent}
        """
        return self.preload_agents(None)


AGENT_REGISTRY = AgentRegistry()
