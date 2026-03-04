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

响应格式:
    统一使用 HttpResult 格式:
    {
        "success": true/false,
        "message": "响应消息",
        "data": null 或 {...}
    }
"""
from fastapi import HTTPException
from pydantic import BaseModel
from typing import Dict, Any

from agent.server.command import CommandHandler, CommandContext
from agent.registry import AGENT_REGISTRY
from agent.server.http.http_result import HttpResult
from agent.server.http.intercepted_router import InterceptedRouter
from agent.server.http.intercept_context import InterceptContext


router = InterceptedRouter(prefix="/command", tags=["命令"])


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


_command_handler = CommandHandler(AGENT_REGISTRY)


def _get_agent(agent_id: str):
    """获取 Agent 实例"""
    if not AGENT_REGISTRY:
        return None
    try:
        return AGENT_REGISTRY.get_agent(agent_id)
    except Exception:
        return None


@router.api("/help", methods=["GET"])
async def get_help(ctx: InterceptContext) -> Dict[str, Any]:
    """获取帮助信息，返回所有可用命令的说明。"""
    help_text = _command_handler.get_help()
    commands_with_prefix = [f"/{cmd}" for cmd in _command_handler.commands.keys()]
    return HttpResult.success(
        message=help_text,
        data={"commands": commands_with_prefix}
    ).to_dict()


@router.api("/new", methods=["POST"])
async def create_new_session(ctx: InterceptContext) -> Dict[str, Any]:
    """创建新会话，为指定用户创建新的对话会话。"""
    request = NewSessionRequest(**ctx.raw)
    agent = _get_agent(request.agent_id)
    if not agent:
        raise HTTPException(status_code=400, detail="Agent 未初始化")
    
    context = CommandContext(
        agent_id=request.agent_id,
        user_id=request.user_id
    )
    
    result = _command_handler.handle("/new", context)
    
    data = {"new_session_id": result.new_session_id} if result.new_session_id else None
    if result.success:
        return HttpResult.success(message=result.message, data=data).to_dict()
    else:
        return HttpResult.error(message=result.message, data=data).to_dict()


@router.api("/clear", methods=["POST"])
async def clear_context(ctx: InterceptContext) -> Dict[str, Any]:
    """清空对话上下文，清空指定会话的对话历史。"""
    request = ClearContextRequest(**ctx.raw)
    agent = _get_agent(request.agent_id)
    if not agent:
        raise HTTPException(status_code=400, detail="Agent 未初始化")
    
    context = CommandContext(
        agent_id=request.agent_id,
        session_id=request.session_id,
        user_id=request.user_id
    )
    
    result = _command_handler.handle("/clear", context)
    
    if result.success:
        return HttpResult.success(message=result.message).to_dict()
    else:
        return HttpResult.error(message=result.message).to_dict()


@router.api("/sessions", methods=["GET"])
async def list_sessions(ctx: InterceptContext) -> Dict[str, Any]:
    """获取会话列表，返回所有会话的列表。"""
    agent_id = ctx.raw.get("agent_id", "default")
    agent = _get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=400, detail="Agent 未初始化")
    
    context = CommandContext(agent_id=agent_id)
    result = _command_handler.handle("/sessions", context)
    
    if result.success:
        return HttpResult.success(message=result.message, data=result.data).to_dict()
    else:
        return HttpResult.error(message=result.message).to_dict()


@router.api("/switch", methods=["POST"])
async def switch_session(ctx: InterceptContext) -> Dict[str, Any]:
    """切换会话，切换到指定序号的会话。"""
    request = SwitchSessionRequest(**ctx.raw)
    agent = _get_agent(request.agent_id)
    if not agent:
        raise HTTPException(status_code=400, detail="Agent 未初始化")
    
    context = CommandContext(
        agent_id=request.agent_id,
        user_id=request.user_id
    )
    
    result = _command_handler.handle(f"/session {request.session_index}", context)
    
    data = {"switched_session_id": result.switched_session_id} if result.switched_session_id else None
    if result.success:
        return HttpResult.success(message=result.message, data=data).to_dict()
    else:
        return HttpResult.error(message=result.message, data=data).to_dict()


@router.api("/models", methods=["GET"])
async def list_models(ctx: InterceptContext) -> Dict[str, Any]:
    """获取模型列表，返回所有可用的模型列表。"""
    agent_id = ctx.raw.get("agent_id", "default")
    context = CommandContext(agent_id=agent_id)
    result = _command_handler.handle("/models", context)
    
    if result.success:
        return HttpResult.success(message=result.message, data=result.data).to_dict()
    else:
        return HttpResult.error(message=result.message).to_dict()


@router.api("/switch-model", methods=["POST"])
async def switch_model(ctx: InterceptContext) -> Dict[str, Any]:
    """切换模型，切换到指定的模型。"""
    request = SwitchModelRequest(**ctx.raw)
    context = CommandContext(agent_id=request.agent_id)
    result = _command_handler.handle(f"/switch {request.model_name}", context)
    
    if result.success:
        return HttpResult.success(message=result.message).to_dict()
    else:
        return HttpResult.error(message=result.message).to_dict()


@router.api("/reload", methods=["POST"])
async def reload_config(ctx: InterceptContext) -> Dict[str, Any]:
    """重载配置，重新加载系统配置和提示词。"""
    context = CommandContext()
    result = _command_handler.handle("/reload", context)
    
    if result.success:
        return HttpResult.success(message=result.message).to_dict()
    else:
        return HttpResult.error(message=result.message).to_dict()
