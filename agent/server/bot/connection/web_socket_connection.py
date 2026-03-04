#!/usr/bin/env python
# -*- coding:utf-8 -*-
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
    """
    
    def __init__(self, url: str, name: str = "", **options):
        super().__init__(name=name, **options)
        self.url = url
        self._access_token = options.get("access_token", "")
        self._heartbeat_message = options.get("heartbeat_message", "")
        self._ping_interval = options.get("ping_interval", 20)
        
        self._ws: Optional[Any] = None
        self._ping_task: Optional[asyncio.Task] = None
    
    async def _do_connect(self) -> bool:
        """建立 WebSocket 连接。"""
        try:
            import websockets
            
            self._log_info(f"正在连接 {self.url}...")
            
            self._ws = await websockets.connect(self.url)
            
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
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
        
        if self._ws:
            try:
                await self._ws.close()
                self._log_info("WebSocket 连接已关闭")
            except Exception as e:
                self._log_error(f"关闭连接错误: {e}")
            finally:
                self._ws = None
    
    async def _do_send(self, data: Any) -> bool:
        """发送 WebSocket 消息。"""
        if not self._ws:
            return False
        
        try:
            if isinstance(data, dict):
                data = json.dumps(data, ensure_ascii=False)
            
            await self._ws.send(data)
            return True
            
        except Exception as e:
            self._log_error(f"发送失败: {e}")
            return False
    
    async def _do_receive(self) -> Any:
        """接收 WebSocket 消息。"""
        if not self._ws:
            raise ConnectionError("未连接")
        
        try:
            import websockets
            
            message = await self._ws.recv()
            
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
                        pong_waiter = await self._ws.ping()
                        await asyncio.wait_for(pong_waiter, timeout=10)
                    except Exception as e:
                        self._log_warning(f"ping 失败: {e}")
                        break
                        
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._log_error(f"ping 循环错误: {e}")
