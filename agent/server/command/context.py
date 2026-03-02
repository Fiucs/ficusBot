#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
命令上下文模块

功能说明:
    - 定义命令执行时的上下文信息
    - 包含 Agent、会话、用户等标识
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class CommandContext:
    """
    命令执行上下文
    
    封装命令执行所需的上下文信息，支持 Bot 和 API 两种模式。
    
    Attributes:
        agent_id: Agent 实例 ID
        session_id: 当前会话 ID
        chat_id: 聊天标识（Bot 模式，格式: platform:user_id）
        user_id: 用户标识（API 模式）
    
    使用示例:
        # Bot 模式
        context = CommandContext(
            agent_id="default",
            session_id="sess_xxx",
            chat_id="feishu:ou_xxx"
        )
        
        # API 模式
        context = CommandContext(
            agent_id="default",
            session_id="sess_xxx",
            user_id="user_123"
        )
    """
    
    agent_id: str = "default"
    session_id: Optional[str] = None
    chat_id: Optional[str] = None
    user_id: Optional[str] = None
    
    @property
    def is_bot_mode(self) -> bool:
        """是否为 Bot 模式"""
        return self.chat_id is not None
    
    @property
    def is_api_mode(self) -> bool:
        """是否为 API 模式"""
        return self.user_id is not None and self.chat_id is None
