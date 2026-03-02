#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
命令结果模块

功能说明:
    - 定义命令执行的结果结构
    - 支持成功/失败状态、消息、额外数据
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class CommandResult:
    """
    命令执行结果
    
    封装命令执行的结果信息，用于返回给调用方。
    
    Attributes:
        success: 命令是否执行成功
        message: 响应消息（显示给用户）
        is_command: 输入是否为命令（False 表示不是命令，继续正常处理）
        data: 额外数据（如会话列表、模型列表等）
        new_session_id: 新创建的会话 ID（用于 /new 命令）
        switched_session_id: 切换后的会话 ID（用于 /session 命令）
    
    使用示例:
        # 是命令，执行成功
        result = CommandResult(
            success=True,
            message="已创建新会话",
            is_command=True,
            new_session_id="sess_xxx"
        )
        
        # 不是命令
        result = CommandResult(
            success=True,
            message="",
            is_command=False
        )
        
        # 命令执行失败
        result = CommandResult(
            success=False,
            message="未知命令: /xxx",
            is_command=True
        )
    """
    
    success: bool = True
    message: str = ""
    is_command: bool = True
    data: Dict[str, Any] = field(default_factory=dict)
    new_session_id: Optional[str] = None
    switched_session_id: Optional[str] = None
    
    @classmethod
    def not_a_command(cls) -> "CommandResult":
        """创建"不是命令"的结果"""
        return cls(
            success=True,
            message="",
            is_command=False
        )
    
    @classmethod
    def success_result(cls, message: str, **kwargs) -> "CommandResult":
        """创建成功结果"""
        return cls(
            success=True,
            message=message,
            is_command=True,
            **kwargs
        )
    
    @classmethod
    def error_result(cls, message: str, **kwargs) -> "CommandResult":
        """创建错误结果"""
        return cls(
            success=False,
            message=message,
            is_command=True,
            **kwargs
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "message": self.message,
            "is_command": self.is_command,
            "data": self.data,
            "new_session_id": self.new_session_id,
            "switched_session_id": self.switched_session_id,
        }
