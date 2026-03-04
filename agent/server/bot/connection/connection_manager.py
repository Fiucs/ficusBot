#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
连接管理器。

集中管理多个连接的生命周期、健康检查和统计信息。
"""

from typing import Dict, List, Optional, Callable
import asyncio
from dataclasses import dataclass, field
from datetime import datetime

from .base import BaseConnection, ConnectionState


@dataclass
class ConnectionInfo:
    """连接信息。"""
    name: str
    connection: BaseConnection
    created_at: datetime = field(default_factory=datetime.now)
    tags: List[str] = field(default_factory=list)


class ConnectionManager:
    """
    连接管理器。
    
    集中管理多个长连接，提供统一的生命周期管理。
    """
    
    def __init__(self, health_check_interval: int = 30):
        self._connections: Dict[str, ConnectionInfo] = {}
        self._health_check_interval = health_check_interval
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False
        
        self.on_connection_error: Optional[Callable[[str, Exception], None]] = None
    
    async def add_connection(self, connection: BaseConnection, tags: Optional[List[str]] = None) -> bool:
        """添加连接。"""
        name = connection.name
        
        if name in self._connections:
            return False
        
        info = ConnectionInfo(
            name=name,
            connection=connection,
            tags=tags or []
        )
        
        self._connections[name] = info
        return True
    
    async def remove_connection(self, name: str, disconnect: bool = True) -> bool:
        """移除连接。"""
        if name not in self._connections:
            return False
        
        info = self._connections[name]
        
        if disconnect and info.connection.is_connected:
            await info.connection.disconnect()
        
        del self._connections[name]
        return True
    
    def get_connection(self, name: str) -> Optional[BaseConnection]:
        """获取连接。"""
        info = self._connections.get(name)
        return info.connection if info else None
    
    def get_connections_by_tag(self, tag: str) -> List[BaseConnection]:
        """根据标签获取连接。"""
        return [
            info.connection for info in self._connections.values()
            if tag in info.tags
        ]
    
    async def start_all(self) -> Dict[str, bool]:
        """启动所有连接。"""
        results = {}
        
        for name, info in self._connections.items():
            try:
                results[name] = await info.connection.connect()
            except Exception:
                results[name] = False
        
        self._start_health_check()
        
        return results
    
    async def stop_all(self) -> None:
        """停止所有连接。"""
        self._stop_health_check()
        
        tasks = [
            info.connection.disconnect()
            for info in self._connections.values()
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def send_to(self, name: str, data) -> bool:
        """向指定连接发送数据。"""
        conn = self.get_connection(name)
        if not conn:
            return False
        
        return await conn.send(data)
    
    async def broadcast(self, data, tag: Optional[str] = None) -> Dict[str, bool]:
        """广播消息。"""
        if tag:
            connections = self.get_connections_by_tag(tag)
        else:
            connections = [info.connection for info in self._connections.values()]
        
        results = {}
        for conn in connections:
            try:
                results[conn.name] = await conn.send(data)
            except Exception:
                results[conn.name] = False
        
        return results
    
    def get_all_stats(self) -> Dict[str, dict]:
        """获取所有连接统计。"""
        return {
            name: {
                "state": info.connection.state.name,
                "connected": info.connection.is_connected,
                "stats": {
                    "connect_count": info.connection.stats.connect_count,
                    "message_sent": info.connection.stats.message_sent,
                    "message_received": info.connection.stats.message_received,
                    "error_count": info.connection.stats.error_count,
                },
                "tags": info.tags,
            }
            for name, info in self._connections.items()
        }
    
    def get_status_summary(self) -> dict:
        """获取状态摘要。"""
        total = len(self._connections)
        connected = sum(
            1 for info in self._connections.values()
            if info.connection.is_connected
        )
        
        return {
            "total": total,
            "connected": connected,
            "disconnected": total - connected,
        }
    
    def _start_health_check(self) -> None:
        """启动健康检查。"""
        if self._health_check_task and not self._health_check_task.done():
            return
        
        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())
    
    def _stop_health_check(self) -> None:
        """停止健康检查。"""
        self._running = False
        
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
    
    async def _health_check_loop(self) -> None:
        """健康检查循环。"""
        while self._running:
            try:
                await asyncio.sleep(self._health_check_interval)
                
                if not self._running:
                    break
                
                for name, info in list(self._connections.items()):
                    conn = info.connection
                    
                    if conn._reconnect_enabled and not conn.is_connected:
                        try:
                            await conn.connect()
                        except Exception as e:
                            if self.on_connection_error:
                                self.on_connection_error(name, e)
                
            except asyncio.CancelledError:
                break
            except Exception:
                pass
