"""
统一连接管理模块。

提供长连接（WebSocket、长轮询等）的统一抽象和管理，
简化各平台监听器的连接实现。
"""

from .base import BaseConnection, ConnectionState
from .websocket import WebSocketConnection
from .manager import ConnectionManager

__all__ = [
    "BaseConnection",
    "ConnectionState",
    "WebSocketConnection",
    "ConnectionManager"
]
