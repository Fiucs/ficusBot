#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
命令处理模块

功能说明:
    - 处理 Bot 模式下的命令（如 /new, /help 等）
    - 提供命令注册和执行机制
    - 支持动态扩展新命令

核心组件:
    - CommandHandler: 命令处理器主类
    - CommandContext: 命令执行上下文
    - CommandResult: 命令执行结果

内置命令:
    /help           - 显示帮助
    /new            - 创建新会话
    /sessions       - 显示会话列表
    /session <n>    - 切换会话
    /clear          - 清空上下文
    /models         - 显示模型列表
    /switch <model> - 切换模型
    /reload         - 重载配置

使用示例:
    from agent.server.command import CommandHandler, CommandContext
    
    handler = CommandHandler(agent_registry)
    
    context = CommandContext(
        agent_id="default",
        session_id="sess_xxx",
        chat_id="feishu:ou_xxx",
        listener="feishu"
    )
    
    result = await handler.handle("/help", context)
    if result.is_command:
        print(result.message)
"""
from .context import CommandContext
from .result import CommandResult
from .handler import CommandHandler

__all__ = [
    "CommandContext",
    "CommandResult", 
    "CommandHandler",
]
