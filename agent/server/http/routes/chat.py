#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
聊天和工具 API 路由模块

功能说明:
    - /api/chat: 聊天接口
    - /api/chat/{agent_id}: 使用指定 Agent 对话
    - /api/chat/stream: 流式聊天接口
    - /api/tools: 获取工具列表
    - /api/skills: 获取技能列表

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

from ..intercepted_router import InterceptedRouter
from ..intercept_context import InterceptContext
from agent.main import get_agent
from agent.server.http.http_result import HttpResult


router = InterceptedRouter()


class ChatRequest(BaseModel):
    """聊天请求模型"""
    message: str
    user_id: str = None
    session_id: str = None


@router.api("/api/chat", methods=["POST"])
async def chat(ctx: InterceptContext) -> Dict[str, Any]:
    """聊天接口（自动拦截）。"""
    agent = get_agent()
    
    try:
        result = agent.chat(ctx.content)
        
        total_prompt_tokens = result.get("total_prompt_tokens", 0)
        total_completion_tokens = result.get("total_completion_tokens", 0)
        total_tokens = total_prompt_tokens + total_completion_tokens
        
        data = {
            "content": result.get("content", ""),
            "user_id": ctx.user_id,
            "session_id": ctx.session_id,
            "elapsed_time": result.get("elapsed_time", 0),
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
            "context_window": result.get("context_window", 0),
            "context_usage_percent": result.get("context_usage_percent", 0),
        }
        
        return HttpResult.success(message="对话完成", data=data).to_dict()
    except Exception as e:
        return HttpResult.error(message=str(e)).to_dict()


@router.api("/api/chat/{agent_id}", methods=["POST"])
async def chat_with_agent(ctx: InterceptContext, agent_id: str) -> Dict[str, Any]:
    """使用指定 Agent 进行对话（自动拦截）。"""
    try:
        agent = get_agent(agent_id)
        result = agent.chat(ctx.content)
        
        total_prompt_tokens = result.get("total_prompt_tokens", 0)
        total_completion_tokens = result.get("total_completion_tokens", 0)
        total_tokens = total_prompt_tokens + total_completion_tokens
        
        data = {
            "content": result.get("content", ""),
            "agent_id": agent_id,
            "elapsed_time": result.get("elapsed_time", 0),
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
            "context_window": result.get("context_window", 0),
            "context_usage_percent": result.get("context_usage_percent", 0),
        }
        
        return HttpResult.success(message="对话完成", data=data).to_dict()
    except ValueError as e:
        return HttpResult.error(message=str(e)).to_dict()
    except Exception as e:
        return HttpResult.error(message=str(e)).to_dict()


@router.api("/api/chat/stream", methods=["POST"])
async def chat_stream(ctx: InterceptContext):
    """流式聊天接口（自动拦截）。"""
    agent = get_agent()
    
    try:
        result = agent.chat_stream(ctx.content)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.api("/api/tools", methods=["GET"])
async def get_tools(ctx: InterceptContext) -> Dict[str, Any]:
    """获取工具列表（自动拦截）。"""
    agent = get_agent()
    return HttpResult.success(message="获取成功", data=agent.tool_adapter.list_tools()).to_dict()


@router.api("/api/skills", methods=["GET"])
async def get_skills(ctx: InterceptContext) -> Dict[str, Any]:
    """获取技能列表（自动拦截）。"""
    agent = get_agent()
    return HttpResult.success(message="获取成功", data=agent.skill_loader.skills).to_dict()
