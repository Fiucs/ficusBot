#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :health.py
# @Time      :2026/03/02
# @Author    :Ficus

"""
健康检查 API 路由模块

功能说明:
    - /health: 健康检查接口（不经过拦截器）

核心方法:
    - health: 健康检查
"""

from fastapi import APIRouter

from agent.main import get_agent

router = APIRouter()  # 普通 Router，不拦截


@router.get("/health")
async def health():
    """
    健康检查（不经过拦截器）。
    
    响应:
        {
            "status": "success",
            "message": "服务运行正常",
            "current_model": "..."
        }
    """
    agent = get_agent()
    return {
        "status": "success",
        "message": "服务运行正常",
        "current_model": agent.llm_client.current_model_alias
    }
