#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :app.py
# @Time      :2026/03/02
# @Author    :Ficus

"""
FastAPI 应用创建模块

功能说明:
    - 创建 FastAPI 应用实例
    - 配置 CORS 中间件
    - 注册所有路由

核心方法:
    - create_app: 创建 FastAPI 应用
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from .intercepted_router import InterceptedRouter
from .routes import chat, health, command


def create_app(gateway=None) -> FastAPI:
    """
    创建 FastAPI 应用。
    
    Args:
        gateway: Gateway 实例（可选）
    
    Returns:
        FastAPI: FastAPI 应用实例
    """
    app = FastAPI(
        title="FicusBot API",
        description="统一网关 API 接口",
        version="3.0"
    )
    
    # CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 配置需要拦截的路由
    if gateway:
        # chat 路由直接共享 Gateway 的拦截器链
        chat.router.set_gateway(gateway)
        chat.router.use_chain(gateway.incoming_chain)
        # command 路由也共享拦截器链
        command.router.set_gateway(gateway)
        command.router.use_chain(gateway.incoming_chain)
    
    # 注册路由
    app.include_router(health.router)    # 不拦截
    app.include_router(chat.router)      # 拦截
    app.include_router(command.router)   # 拦截
    
    logger.info("[HTTP] FastAPI 应用已创建")
    return app
