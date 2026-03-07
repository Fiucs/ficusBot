#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :application.py
# @Time      :2026/03/07
# @Author    :Ficus

"""
应用程序模块

该模块实现应用程序单例，全局管理消息通道。
"""
import threading
from typing import Optional, TYPE_CHECKING
from loguru import logger

from agent.core.messaging.channel import MessageChannel

if TYPE_CHECKING:
    from agent.registry import AgentRegistry


class Application:
    """
    应用程序 - 单例模式，全局管理消息通道
    
    功能说明:
        - 管理全局唯一的消息通道
        - 支持 AgentRegistry 注入
        - 提供统一的通道获取接口
        - 支持多 Agent 架构
    
    核心方法:
        - get_instance: 获取单例实例
        - with_registry: 使用注册中心创建实例
        - initialize: 初始化消息通道
        - channel: 获取消息通道属性
    
    使用示例:
        # 获取全局通道
        from agent.core.messaging import get_channel
        channel = get_channel()
        
        # 使用注册中心
        app = Application.with_registry(AGENT_REGISTRY)
        channel = app.initialize()
    """
    
    _instance: Optional["Application"] = None
    _lock = threading.RLock()
    
    def __new__(cls) -> "Application":
        """单例模式：确保全局只有一个实例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    logger.debug(f"[Application] 创建新的 Application 实例")
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
                else:
                    logger.debug(f"[Application] 返回已存在的 Application 实例（双重检查后）")
        else:
            logger.debug(f"[Application] 返回已存在的 Application 实例")
        return cls._instance
    
    def __init__(self):
        """初始化应用程序"""
        if self._initialized:
            logger.debug(f"[Application] 实例已初始化，跳过")
            return
        logger.debug(f"[Application] 初始化应用程序实例")
        self._channel: Optional[MessageChannel] = None
        self._registry: Optional["AgentRegistry"] = None
        self._initialized = True
    
    @classmethod
    def get_instance(cls) -> "Application":
        """获取单例实例"""
        logger.debug(f"[Application] get_instance() 被调用")
        return cls()
    
    @classmethod
    def with_registry(cls, registry: "AgentRegistry") -> "Application":
        """
        使用注册中心创建实例
        
        Args:
            registry: Agent 注册中心实例
            
        Returns:
            Application 实例
        """
        logger.debug(f"[Application] with_registry() 被调用，注册中心类型: {type(registry).__name__}")
        instance = cls()
        instance._registry = registry
        logger.debug(f"[Application] 已注入 AgentRegistry，可用 Agent 数量: {len(registry.list_agents()) if registry else 0}")
        return instance
    
    def initialize(self) -> MessageChannel:
        """
        初始化消息通道
        
        Returns:
            MessageChannel 实例
        """
        if self._channel is None:
            logger.debug(f"[Application] 创建新的 MessageChannel")
            self._channel = MessageChannel()
        else:
            logger.debug(f"[Application] 返回已存在的 MessageChannel")
        return self._channel
    
    @property
    def channel(self) -> MessageChannel:
        """获取消息通道"""
        if self._channel is None:
            logger.debug(f"[Application] channel 属性访问，通道未初始化，正在初始化...")
            self.initialize()
        return self._channel
    
    @property
    def registry(self) -> Optional["AgentRegistry"]:
        """获取 Agent 注册中心"""
        logger.debug(f"[Application] registry 属性访问，有注册中心: {self._registry is not None}")
        return self._registry
    
    def reset(self) -> None:
        """
        重置应用程序状态
        
        用于测试或重新初始化。
        """
        logger.debug(f"[Application] 重置应用程序状态")
        logger.debug(f"[Application] 重置前 - 通道: {self._channel is not None}, 注册中心: {self._registry is not None}")
        self._channel = None
        self._registry = None
        logger.debug(f"[Application] 重置完成")


def get_channel() -> MessageChannel:
    """
    全局获取通道
    
    Returns:
        MessageChannel 实例
    """
    logger.debug(f"[Application] get_channel() 全局函数被调用")
    return Application.get_instance().channel


def get_application() -> Application:
    """
    获取应用程序实例
    
    Returns:
        Application 实例
    """
    logger.debug(f"[Application] get_application() 全局函数被调用")
    return Application.get_instance()
