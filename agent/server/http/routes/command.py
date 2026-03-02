#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
命令路由模块

功能说明:
    - 提供 API 模式的命令接口
    - 会话管理（创建、切换、列表）
    - 模型管理（列表、切换）
    - 系统管理（重载配置）

接口列表:
    POST /command/new          - 创建新会话
    POST /command/clear        - 清空上下文
    GET  /command/sessions     - 获取会话列表
    POST /command/switch       - 切换会话
    GET  /command/models       - 获取模型列表
    POST /command/switch-model - 切换模型
    POST /command/reload       - 重载配置
    GET  /command/help         - 获取帮助

使用示例:
    # 创建新会话
    POST /command/new
    {
        "user_id": "user_123",
        "session_id": "optional_existing_session"
    }
    
    # 切换会话
    POST /command/switch
    {
        "user_id": "user_123",
        "session_index": 1
    }
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from loguru import logger

from agent.server.command import CommandHandler, CommandContext, CommandResult
from agent.registry import AGENT_REGISTRY


router = APIRouter(prefix="/command", tags=["命令"])


class NewSessionRequest(BaseModel):
    """创建新会话请求"""
    user_id: str
    agent_id: str = "default"


class ClearContextRequest(BaseModel):
    """清空上下文请求"""
    user_id: str
    session_id: str
    agent_id: str = "default"


class SwitchSessionRequest(BaseModel):
    """切换会话请求"""
    user_id: str
    session_index: int
    agent_id: str = "default"


class SwitchModelRequest(BaseModel):
    """切换模型请求"""
    model_name: str
    agent_id: str = "default"


class CommandResponse(BaseModel):
    """命令响应"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


_command_handler = CommandHandler(AGENT_REGISTRY)


def _get_agent(agent_id: str):
    """获取 Agent 实例"""
    if not AGENT_REGISTRY:
        return None
    try:
        return AGENT_REGISTRY.get_agent(agent_id)
    except Exception:
        return None


@router.get("/help", response_model=CommandResponse)
async def get_help():
    """
    获取帮助信息
    
    返回所有可用命令的说明。
    """
    help_text = _command_handler.get_help()
    return CommandResponse(
        success=True,
        message=help_text,
        data={"commands": list(_command_handler.commands.keys())}
    )


@router.post("/new", response_model=CommandResponse)
async def create_new_session(request: NewSessionRequest):
    """
    创建新会话
    
    为指定用户创建新的对话会话。
    """
    agent = _get_agent(request.agent_id)
    if not agent:
        raise HTTPException(status_code=400, detail="Agent 未初始化")
    
    context = CommandContext(
        agent_id=request.agent_id,
        user_id=request.user_id
    )
    
    result = _command_handler.handle("/new", context)
    
    return CommandResponse(
        success=result.success,
        message=result.message,
        data={"new_session_id": result.new_session_id} if result.new_session_id else None
    )


@router.post("/clear", response_model=CommandResponse)
async def clear_context(request: ClearContextRequest):
    """
    清空对话上下文
    
    清空指定会话的对话历史。
    """
    agent = _get_agent(request.agent_id)
    if not agent:
        raise HTTPException(status_code=400, detail="Agent 未初始化")
    
    context = CommandContext(
        agent_id=request.agent_id,
        session_id=request.session_id,
        user_id=request.user_id
    )
    
    result = _command_handler.handle("/clear", context)
    
    return CommandResponse(
        success=result.success,
        message=result.message
    )


@router.get("/sessions", response_model=CommandResponse)
async def list_sessions(agent_id: str = "default"):
    """
    获取会话列表
    
    返回所有会话的列表。
    """
    agent = _get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=400, detail="Agent 未初始化")
    
    context = CommandContext(
        agent_id=agent_id
    )
    
    result = _command_handler.handle("/sessions", context)
    
    return CommandResponse(
        success=result.success,
        message=result.message,
        data=result.data
    )


@router.post("/switch", response_model=CommandResponse)
async def switch_session(request: SwitchSessionRequest):
    """
    切换会话
    
    切换到指定序号的会话。
    """
    agent = _get_agent(request.agent_id)
    if not agent:
        raise HTTPException(status_code=400, detail="Agent 未初始化")
    
    context = CommandContext(
        agent_id=request.agent_id,
        user_id=request.user_id
    )
    
    result = _command_handler.handle(f"/session {request.session_index}", context)
    
    return CommandResponse(
        success=result.success,
        message=result.message,
        data={"switched_session_id": result.switched_session_id} if result.switched_session_id else None
    )


@router.get("/models", response_model=CommandResponse)
async def list_models(agent_id: str = "default"):
    """
    获取模型列表
    
    返回所有可用的模型列表。
    """
    context = CommandContext(
        agent_id=agent_id
    )
    
    result = _command_handler.handle("/models", context)
    
    return CommandResponse(
        success=result.success,
        message=result.message,
        data=result.data
    )


@router.post("/switch-model", response_model=CommandResponse)
async def switch_model(request: SwitchModelRequest):
    """
    切换模型
    
    切换到指定的模型。
    """
    context = CommandContext(
        agent_id=request.agent_id
    )
    
    result = _command_handler.handle(f"/switch {request.model_name}", context)
    
    return CommandResponse(
        success=result.success,
        message=result.message
    )


@router.post("/reload", response_model=CommandResponse)
async def reload_config():
    """
    重载配置
    
    重新加载系统配置和提示词。
    """
    context = CommandContext()
    
    result = _command_handler.handle("/reload", context)
    
    return CommandResponse(
        success=result.success,
        message=result.message
    )
