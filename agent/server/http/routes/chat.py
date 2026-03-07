#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
聊天和工具 API 路由模块

功能说明:
    - /api/chat: 非流式聊天接口（通过消息层）
    - /api/chat/stream: 流式聊天接口（直接调用 Agent）
    - /api/chat/stream/{agent_id}: 流式聊天接口（指定 Agent）
    - /api/tools: 获取工具列表
    - /api/skills: 获取技能列表
    - /api/agents: 获取可用 Agent 列表

响应格式:
    统一使用 HttpResult 格式:
    {
        "success": true/false,
        "message": "响应消息",
        "data": null 或 {...}
    }
"""

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

from ..intercepted_router import InterceptedRouter
from ..intercept_context import InterceptContext
from agent.main import get_agent
from agent.server.http.http_result import HttpResult


router = InterceptedRouter()


class ChatRequest(BaseModel):
    """
    聊天请求模型
    
    Attributes:
        content: 消息内容
        user_id: 用户ID
        session_id: 会话ID
        target_agent: 目标 Agent ID（单播）
        target_agents: 目标 Agent ID 列表（多播）
        broadcast: 是否广播到所有 Agent
    """
    content: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    target_agent: Optional[str] = None
    target_agents: Optional[List[str]] = None
    broadcast: bool = False


# ============================================================================
# 聊天接口：使用消息层
# ============================================================================

@router.api("/api/chat", methods=["POST"])
async def chat(request: ChatRequest) -> Dict[str, Any]:
    """
    非流式聊天接口（通过消息层）
    
    支持三种路由模式：
    - 单播: 设置 target_agent = "agent_id"
    - 多播: 设置 target_agents = ["agent1", "agent2"]
    - 广播: 设置 broadcast = True
    
    Returns:
        HttpResult 格式的响应
    """
    from agent.core.messaging import (
        Message, MessageSource, MessageType, get_channel
    )
    
    try:
        metadata = {}
        
        if request.target_agent:
            metadata["target_agent"] = request.target_agent
        if request.target_agents:
            metadata["target_agents"] = request.target_agents
        if request.broadcast:
            metadata["broadcast"] = True
        
        message = Message.create(
            source=MessageSource.API,
            type=MessageType.CHAT,
            content=request.content,
            user_id=request.user_id or "",
            session_id=request.session_id,
            metadata=metadata
        )
        
        channel = get_channel()
        response = await channel.publish(message, wait_for_response=True, timeout=120.0)
        
        if response is None:
            return HttpResult.error(message="无处理器响应").to_dict()
        
        data = {
            "content": response.content,
            "success": response.success,
            "error": response.error,
            "message_id": response.message_id,
            "metadata": response.metadata,
            "responses": response.responses
        }
        
        if response.success:
            return HttpResult.success(message="消息处理完成", data=data).to_dict()
        else:
            return HttpResult.error(message=response.error or "处理失败", data=data).to_dict()
            
    except Exception as e:
        return HttpResult.error(message=str(e)).to_dict()


@router.api("/api/chat/stream", methods=["POST"])
async def chat_stream(ctx: InterceptContext):
    """
    流式聊天接口（直接调用默认 Agent）
    
    注意：流式接口暂不支持消息层路由，直接调用默认 Agent。
    
    Returns:
        StreamingResponse: SSE 流式响应
    """
    agent = get_agent()
    
    try:
        async def generate():
            async for chunk in agent.chat_stream(ctx.content):
                yield chunk
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.api("/api/chat/stream/{agent_id}", methods=["POST"])
async def chat_stream_with_agent(ctx: InterceptContext, agent_id: str):
    """
    流式聊天接口（指定 Agent）
    
    Args:
        agent_id: Agent ID
        
    Returns:
        StreamingResponse: SSE 流式响应
    """
    try:
        agent = get_agent(agent_id)
        
        async def generate():
            async for chunk in agent.chat_stream(ctx.content):
                yield chunk
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# 工具和技能接口
# ============================================================================

@router.api("/api/tools", methods=["GET"])
async def get_tools(ctx: InterceptContext) -> Dict[str, Any]:
    """获取工具列表"""
    agent = get_agent()
    return HttpResult.success(message="获取成功", data=agent.tool_adapter.list_tools()).to_dict()


@router.api("/api/skills", methods=["GET"])
async def get_skills(ctx: InterceptContext) -> Dict[str, Any]:
    """获取技能列表"""
    agent = get_agent()
    return HttpResult.success(message="获取成功", data=agent.skill_loader.skills).to_dict()


@router.api("/api/agents", methods=["GET"])
async def list_agents(ctx: InterceptContext) -> Dict[str, Any]:
    """获取可用 Agent 列表"""
    from agent.registry import AGENT_REGISTRY
    
    agents = []
    for agent_id in AGENT_REGISTRY.list_agents():
        config = AGENT_REGISTRY.get_config(agent_id)
        agents.append({
            "id": agent_id,
            "description": config.description if config else "",
            "model": config.model if config else ""
        })
    
    return HttpResult.success(message="获取成功", data={"agents": agents}).to_dict()
