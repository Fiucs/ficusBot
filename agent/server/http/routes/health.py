#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
健康检查 API 路由模块

功能说明:
    - /health: 健康检查接口（不经过拦截器）

响应格式:
    统一使用 HttpResult 格式:
    {
        "success": true/false,
        "message": "响应消息",
        "data": null 或 {...}
    }
"""

from fastapi import APIRouter
from typing import Dict, Any

from agent.main import get_agent
from agent.server.http.http_result import HttpResult


router = APIRouter()


@router.get("/health")
async def health() -> Dict[str, Any]:
    """健康检查（不经过拦截器）。"""
    agent = get_agent()
    return HttpResult.success(
        message="服务运行正常",
        data={"current_model": agent.llm_client.current_model_alias}
    ).to_dict()
