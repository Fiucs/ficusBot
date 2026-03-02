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
    
    集中管理多个长连接，提供：
        - 统一的生命周期管理
        - 健康状态监控
        - 统计信息聚合
        - 批量操作
    
    使用示例:
        ```python
        manager = ConnectionManager()
        
        # 添加连接
        conn = WebSocketConnection("ws://example.com", name="bot1")
        await manager.add_connection(conn)
        
        # 启动所有连接
        await manager.start_all()
        
        # 获取统计
        stats = manager.get_all_stats()
        ```
    
    核心功能:
        - 连接注册和注销
        - 批量启动/停止
        - 健康检查
        - 状态监控
    """
    
    def __init__(self, health_check_interval: int = 30):
        """
        初始化连接管理器。
        
        参数:
            health_check_interval: 健康检查间隔（秒）
        """
        self._connections: Dict[str, ConnectionInfo] = {}
        self._health_check_interval = health_check_interval
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False
        
        # 事件回调
        self.on_connection_error: Optional[Callable[[str, Exception], None]] = None
    
    async def add_connection(self, connection: BaseConnection, tags: Optional[List[str]] = None) -> bool:
        """
        添加连接。
        
        参数:
            connection: 连接实例
            tags: 标签列表（用于分组管理）
        
        返回:
            bool: 是否添加成功
        """
        name = connection.name
        
        if name in self._connections:
            print(f"[ConnectionManager] 连接已存在: {name}")
            return False
        
        info = ConnectionInfo(
            name=name,
            connection=connection,
            tags=tags or []
        )
        
        self._connections[name] = info
        print(f"[ConnectionManager] 添加连接: {name}")
        return True
    
    async def remove_connection(self, name: str, disconnect: bool = True) -> bool:
        """
        移除连接。
        
        参数:
            name: 连接名称
            disconnect: 是否先断开连接
        
        返回:
            bool: 是否移除成功
        """
        if name not in self._connections:
            return False
        
        info = self._connections[name]
        
        if disconnect and info.connection.is_connected:
            await info.connection.disconnect()
        
        del self._connections[name]
        print(f"[ConnectionManager] 移除连接: {name}")
        return True
    
    def get_connection(self, name: str) -> Optional[BaseConnection]:
        """
        获取连接。
        
        参数:
            name: 连接名称
        
        返回:
            连接实例，不存在则返回 None
        """
        info = self._connections.get(name)
        return info.connection if info else None
    
    def get_connections_by_tag(self, tag: str) -> List[BaseConnection]:
        """
        根据标签获取连接。
        
        参数:
            tag: 标签名称
        
        返回:
            连接列表
        """
        return [
            info.connection for info in self._connections.values()
            if tag in info.tags
        ]
    
    async def start_all(self) -> Dict[str, bool]:
        """
        启动所有连接。
        
        返回:
            Dict[str, bool]: 各连接启动结果
        """
        results = {}
        
        print(f"[ConnectionManager] 启动 {len(self._connections)} 个连接...")
        
        # 并发启动
        tasks = []
        for name, info in self._connections.items():
            task = self._start_connection(name, info.connection)
            tasks.append((name, task))
        
        for name, task in tasks:
            try:
                results[name] = await task
            except Exception as e:
                print(f"[ConnectionManager] 启动 {name} 异常: {e}")
                results[name] = False
        
        # 启动健康检查
        self._start_health_check()
        
        success_count = sum(1 for r in results.values() if r)
        print(f"[ConnectionManager] 启动完成: {success_count}/{len(results)} 成功")
        
        return results
    
    async def _start_connection(self, name: str, connection: BaseConnection) -> bool:
        """启动单个连接。"""
        try:
            return await connection.connect()
        except Exception as e:
            print(f"[ConnectionManager] 启动 {name} 失败: {e}")
            return False
    
    async def stop_all(self) -> None:
        """停止所有连接。"""
        print(f"[ConnectionManager] 停止 {len(self._connections)} 个连接...")
        
        # 停止健康检查
        self._stop_health_check()
        
        # 并发停止
        tasks = [
            info.connection.disconnect()
            for info in self._connections.values()
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
        print("[ConnectionManager] 所有连接已停止")
    
    async def send_to(self, name: str, data) -> bool:
        """
        向指定连接发送数据。
        
        参数:
            name: 连接名称
            data: 要发送的数据
        
        返回:
            bool: 发送是否成功
        """
        conn = self.get_connection(name)
        if not conn:
            print(f"[ConnectionManager] 连接不存在: {name}")
            return False
        
        return await conn.send(data)
    
    async def broadcast(self, data, tag: Optional[str] = None) -> Dict[str, bool]:
        """
        广播消息。
        
        参数:
            data: 要发送的数据
            tag: 标签过滤（可选）
        
        返回:
            Dict[str, bool]: 各连接发送结果
        """
        if tag:
            connections = self.get_connections_by_tag(tag)
        else:
            connections = [info.connection for info in self._connections.values()]
        
        results = {}
        for conn in connections:
            try:
                results[conn.name] = await conn.send(data)
            except Exception as e:
                print(f"[ConnectionManager] 发送到 {conn.name} 失败: {e}")
                results[conn.name] = False
        
        return results
    
    def get_all_stats(self) -> Dict[str, dict]:
        """
        获取所有连接统计。
        
        返回:
            Dict[str, dict]: 各连接统计信息
        """
        return {
            name: {
                "state": info.connection.state.name,
                "connected": info.connection.is_connected,
                "stats": {
                    "connect_count": info.connection.stats.connect_count,
                    "disconnect_count": info.connection.stats.disconnect_count,
                    "message_sent": info.connection.stats.message_sent,
                    "message_received": info.connection.stats.message_received,
                    "error_count": info.connection.stats.error_count,
                },
                "tags": info.tags,
                "created_at": info.created_at.isoformat()
            }
            for name, info in self._connections.items()
        }
    
    def get_status_summary(self) -> dict:
        """
        获取状态摘要。
        
        返回:
            dict: 状态摘要
        """
        total = len(self._connections)
        connected = sum(
            1 for info in self._connections.values()
            if info.connection.is_connected
        )
        
        state_counts = {}
        for info in self._connections.values():
            state = info.connection.state.name
            state_counts[state] = state_counts.get(state, 0) + 1
        
        return {
            "total": total,
            "connected": connected,
            "disconnected": total - connected,
            "states": state_counts
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
                
                # 检查每个连接
                for name, info in list(self._connections.items()):
                    conn = info.connection
                    
                    # 检查是否应该连接但未连接
                    if conn._reconnect_enabled and not conn.is_connected:
                        print(f"[ConnectionManager] 检测到 {name} 断开，尝试重连...")
                        try:
                            await conn.connect()
                        except Exception as e:
                            print(f"[ConnectionManager] {name} 重连失败: {e}")
                            if self.on_connection_error:
                                self.on_connection_error(name, e)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[ConnectionManager] 健康检查错误: {e}")
