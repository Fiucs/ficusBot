"""
WebSocket 连接实现。

基于 websockets 库的统一 WebSocket 连接管理。
"""

from typing import Any, Optional
import asyncio
import json

from .base import BaseConnection, ConnectionState


class WebSocketConnection(BaseConnection):
    """
    WebSocket 连接实现。
    
    特性:
        - 自动重连
        - 心跳保活
        - 支持文本和二进制消息
        - 支持认证
    
    使用示例:
        ```python
        conn = WebSocketConnection(
            url="ws://localhost:3001",
            name="QQBot",
            heartbeat_interval=30
        )
        conn.on_message = handle_message
        await conn.connect()
        ```
    
    配置项:
        - url: WebSocket 地址
        - access_token: 认证令牌（可选）
        - heartbeat_message: 心跳消息内容（默认空）
        - ping_interval: 发送 ping 间隔（秒）
    """
    
    def __init__(self, url: str, name: str = "", **options):
        """
        初始化 WebSocket 连接。
        
        参数:
            url: WebSocket 连接地址
            name: 连接名称
            **options: 配置选项
                - access_token: 认证令牌
                - heartbeat_message: 心跳消息
                - ping_interval: ping 间隔
        """
        super().__init__(name=name, **options)
        self.url = url
        self._access_token = options.get("access_token", "")
        self._heartbeat_message = options.get("heartbeat_message", "")
        self._ping_interval = options.get("ping_interval", 20)
        
        self._ws: Optional[Any] = None
        self._ping_task: Optional[asyncio.Task] = None
    
    async def _do_connect(self) -> bool:
        """
        建立 WebSocket 连接。
        
        返回:
            bool: 连接是否成功
        """
        try:
            import websockets
            
            self._log_info(f"正在连接 {self.url}...")
            
            # 建立连接
            self._ws = await websockets.connect(self.url)
            
            # 发送认证（如果有 token）
            if self._access_token:
                auth_msg = {
                    "action": "authenticate",
                    "params": {"token": self._access_token}
                }
                await self._ws.send(json.dumps(auth_msg))
                self._log_info("已发送认证信息")
            
            self._log_info("✅ WebSocket 连接成功")
            return True
            
        except ImportError:
            self._log_error("缺少依赖: websockets, 请安装: pip install websockets")
            return False
        except Exception as e:
            self._log_error(f"连接失败: {e}")
            return False
    
    async def _do_disconnect(self) -> None:
        """断开 WebSocket 连接。"""
        # 停止 ping 任务
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
        
        # 关闭连接
        if self._ws:
            try:
                await self._ws.close()
                self._log_info("WebSocket 连接已关闭")
            except Exception as e:
                self._log_error(f"关闭连接错误: {e}")
            finally:
                self._ws = None
    
    async def _do_send(self, data: Any) -> bool:
        """
        发送 WebSocket 消息。
        
        参数:
            data: 要发送的数据（字符串或字典）
        
        返回:
            bool: 发送是否成功
        """
        if not self._ws:
            return False
        
        try:
            # 自动转换字典为 JSON
            if isinstance(data, dict):
                data = json.dumps(data, ensure_ascii=False)
            
            await self._ws.send(data)
            return True
            
        except Exception as e:
            self._log_error(f"发送失败: {e}")
            return False
    
    async def _do_receive(self) -> Any:
        """
        接收 WebSocket 消息。
        
        返回:
            接收到的数据（字符串或解析后的 JSON）
        
        异常:
            ConnectionError: 连接断开时抛出
        """
        if not self._ws:
            raise ConnectionError("未连接")
        
        try:
            import websockets
            
            message = await self._ws.recv()
            
            # 尝试解析 JSON
            try:
                return json.loads(message)
            except json.JSONDecodeError:
                return message
                
        except websockets.exceptions.ConnectionClosed:
            raise ConnectionError("连接已关闭")
        except Exception as e:
            raise ConnectionError(f"接收错误: {e}")
    
    async def _send_heartbeat(self) -> None:
        """发送心跳消息。"""
        if self._heartbeat_message:
            await self.send(self._heartbeat_message)
    
    def _start_background_tasks(self) -> None:
        """启动后台任务。"""
        super()._start_background_tasks()
        
        # 启动 ping 任务（保持连接活跃）
        self._ping_task = asyncio.create_task(self._ping_loop())
    
    async def _stop_background_tasks(self) -> None:
        """停止后台任务。"""
        await super()._stop_background_tasks()
        
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
    
    async def _ping_loop(self) -> None:
        """发送 ping 保持连接。"""
        try:
            import websockets
            
            while self._running and self.is_connected and self._ws:
                await asyncio.sleep(self._ping_interval)
                
                if self._ws and self.is_connected:
                    try:
                        # 发送 ping
                        pong_waiter = await self._ws.ping()
                        await asyncio.wait_for(pong_waiter, timeout=10)
                    except Exception as e:
                        self._log_warning(f"ping 失败: {e}")
                        break
                        
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._log_error(f"ping 循环错误: {e}")
