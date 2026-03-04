#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
连接管理模块。

功能说明:
    - 提供统一的连接抽象
    - WebSocket 长连接管理
    - 自动重连和心跳保活
"""

from .base import BaseConnection, ConnectionState, ConnectionStats
from .web_socket_connection import WebSocketConnection
from .connection_manager import ConnectionManager, ConnectionInfo

__all__ = [
    "BaseConnection",
    "ConnectionState",
    "ConnectionStats",
    "WebSocketConnection",
    "ConnectionManager",
    "ConnectionInfo",
]
