#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :chat.py
# @Time      :2026/03/02
# @Author    :Ficus

"""
聊天和工具 API 路由模块

功能说明:
    - /api/chat: 聊天接口
    - /api/chat/{agent_id}: 使用指定 Agent 对话
    - /api/chat/stream: 流式聊天接口
    - /api/tools: 获取工具列表
    - /api/skills: 获取技能列表

核心方法:
    - chat: 聊天接口
    - chat_with_agent: 使用指定 Agent 对话
    - chat_stream: 流式聊天接口
    - get_tools: 获取工具列表
    - get_skills: 获取技能列表
"""

from fastapi import HTTPException
from pydantic import BaseModel

from ..router import InterceptedRouter, InterceptContext
from agent.main import get_agent

router = InterceptedRouter()


class ChatRequest(BaseModel):
    """聊天请求模型"""
    message: str
    user_id: str = None
    session_id: str = None


@router.api("/api/chat", methods=["POST"])
async def chat(ctx: InterceptContext):
    """
    聊天接口（自动拦截）。
    
    请求体:
        {
            "message": "你好",
            "user_id": "user_123",     # 可选
            "session_id": "session_1"  # 可选
        }
    
    响应:
        {
            "status": "success",
            "content": "回答内容...",
            "user_id": "user_123",
            "session_id": "session_1",
            "elapsed_time": 1.70,              # 耗时（秒）
            "total_prompt_tokens": 3966,       # 输入 token 数
            "total_completion_tokens": 41,     # 输出 token 数
            "total_tokens": 4007,              # 总 token 数
            "context_window": 128000,          # 上下文窗口大小
            "context_usage_percent": 1.3       # 上下文使用百分比
        }
    """
    agent = get_agent()
    
    try:
        result = agent.chat(ctx.content)
        
        total_prompt_tokens = result.get("total_prompt_tokens", 0)
        total_completion_tokens = result.get("total_completion_tokens", 0)
        total_tokens = total_prompt_tokens + total_completion_tokens
        
        return {
            "status": "success",
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.api("/api/chat/{agent_id}", methods=["POST"])
async def chat_with_agent(ctx: InterceptContext, agent_id: str):
    """
    使用指定 Agent 进行对话（自动拦截）。
    
    Args:
        agent_id: Agent ID
    
    请求体:
        {
            "message": "你好"
        }
    
    响应:
        {
            "status": "success",
            "content": "回答内容...",
            "agent_id": "xxx",
            "elapsed_time": 1.70,              # 耗时（秒）
            "total_prompt_tokens": 3966,       # 输入 token 数
            "total_completion_tokens": 41,     # 输出 token 数
            "total_tokens": 4007,              # 总 token 数
            "context_window": 128000,          # 上下文窗口大小
            "context_usage_percent": 1.3       # 上下文使用百分比
        }
    """
    try:
        agent = get_agent(agent_id)
        result = agent.chat(ctx.content)
        
        total_prompt_tokens = result.get("total_prompt_tokens", 0)
        total_completion_tokens = result.get("total_completion_tokens", 0)
        total_tokens = total_prompt_tokens + total_completion_tokens
        
        return {
            "status": "success",
            "content": result.get("content", ""),
            "agent_id": agent_id,
            "elapsed_time": result.get("elapsed_time", 0),
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
            "context_window": result.get("context_window", 0),
            "context_usage_percent": result.get("context_usage_percent", 0),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.api("/api/chat/stream", methods=["POST"])
async def chat_stream(ctx: InterceptContext):
    """
    流式聊天接口（自动拦截）。
    
    请求体:
        {
            "message": "你好"
        }
    
    响应:
        流式响应
    """
    agent = get_agent()
    
    try:
        result = agent.chat_stream(ctx.content)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.api("/api/tools", methods=["GET"])
async def get_tools(ctx: InterceptContext):
    """
    获取工具列表（自动拦截）。
    
    响应:
        {
            "status": "success",
            "data": [...]
        }
    """
    agent = get_agent()
    return {"status": "success", "data": agent.tool_adapter.list_tools()}


@router.api("/api/skills", methods=["GET"])
async def get_skills(ctx: InterceptContext):
    """
    获取技能列表（自动拦截）。
    
    响应:
        {
            "status": "success",
            "data": {...}
        }
    """
    agent = get_agent()
    return {"status": "success", "data": agent.skill_loader.skills}
