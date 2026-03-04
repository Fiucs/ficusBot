"""
连接抽象基类。

定义所有连接类型的通用接口和状态管理。
"""

from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Any, Callable, Optional, Dict
import asyncio
import time
from dataclasses import dataclass


class ConnectionState(Enum):
    """连接状态枚举。"""
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    RECONNECTING = auto()
    ERROR = auto()


@dataclass
class ConnectionStats:
    """连接统计信息。"""
    connect_count: int = 0
    disconnect_count: int = 0
    message_sent: int = 0
    message_received: int = 0
    error_count: int = 0
    last_connect_time: Optional[float] = None
    last_message_time: Optional[float] = None


class BaseConnection(ABC):
    """
    连接抽象基类。
    
    所有长连接类型（WebSocket、长轮询等）的基类，
    提供统一的生命周期管理和事件处理。
    """
    
    def __init__(self, name: str = "", **options):
        self.name = name or self.__class__.__name__
        self.options = options
        
        self._state = ConnectionState.DISCONNECTED
        self._state_lock = asyncio.Lock()
        self._stats = ConnectionStats()
        
        self._reconnect_enabled = options.get("reconnect_enabled", True)
        self._reconnect_interval = options.get("reconnect_interval", 5)
        self._max_reconnect_attempts = options.get("max_reconnect_attempts", 0)
        self._heartbeat_enabled = options.get("heartbeat_enabled", True)
        self._heartbeat_interval = options.get("heartbeat_interval", 30)
        
        self._running = False
        self._reconnect_count = 0
        
        self.on_connect: Optional[Callable[[], None]] = None
        self.on_disconnect: Optional[Callable[[], None]] = None
        self.on_message: Optional[Callable[[Any], None]] = None
        self.on_error: Optional[Callable[[Exception], None]] = None
        
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._receive_task: Optional[asyncio.Task] = None
    
    @property
    def state(self) -> ConnectionState:
        """获取当前连接状态。"""
        return self._state
    
    @property
    def is_connected(self) -> bool:
        """是否已连接。"""
        return self._state == ConnectionState.CONNECTED
    
    @property
    def stats(self) -> ConnectionStats:
        """获取连接统计。"""
        return self._stats
    
    async def _set_state(self, state: ConnectionState) -> None:
        """设置连接状态。"""
        async with self._state_lock:
            self._state = state
    
    @abstractmethod
    async def _do_connect(self) -> bool:
        """实际连接逻辑（子类实现）。"""
        pass
    
    @abstractmethod
    async def _do_disconnect(self) -> None:
        """实际断开逻辑（子类实现）。"""
        pass
    
    @abstractmethod
    async def _do_send(self, data: Any) -> bool:
        """实际发送逻辑（子类实现）。"""
        pass
    
    @abstractmethod
    async def _do_receive(self) -> Any:
        """实际接收逻辑（子类实现）。"""
        pass
    
    async def connect(self) -> bool:
        """建立连接。"""
        if self.is_connected:
            return True
        
        await self._set_state(ConnectionState.CONNECTING)
        self._running = True
        
        while self._running:
            try:
                success = await self._do_connect()
                if success:
                    await self._set_state(ConnectionState.CONNECTED)
                    self._stats.connect_count += 1
                    self._stats.last_connect_time = time.time()
                    self._reconnect_count = 0
                    
                    self._start_background_tasks()
                    
                    if self.on_connect:
                        try:
                            self.on_connect()
                        except Exception as e:
                            self._log_error(f"on_connect 回调错误: {e}")
                    
                    return True
                
            except Exception as e:
                self._stats.error_count += 1
                self._log_error(f"连接失败: {e}")
            
            if not self._reconnect_enabled:
                await self._set_state(ConnectionState.ERROR)
                return False
            
            if self._max_reconnect_attempts > 0 and self._reconnect_count >= self._max_reconnect_attempts:
                await self._set_state(ConnectionState.ERROR)
                return False
            
            self._reconnect_count += 1
            await self._set_state(ConnectionState.RECONNECTING)
            await asyncio.sleep(self._reconnect_interval)
        
        return False
    
    async def disconnect(self) -> None:
        """断开连接。"""
        self._running = False
        await self._stop_background_tasks()
        
        try:
            await self._do_disconnect()
        except Exception as e:
            self._log_error(f"断开连接错误: {e}")
        
        await self._set_state(ConnectionState.DISCONNECTED)
        self._stats.disconnect_count += 1
        
        if self.on_disconnect:
            try:
                self.on_disconnect()
            except Exception as e:
                self._log_error(f"on_disconnect 回调错误: {e}")
    
    async def send(self, data: Any) -> bool:
        """发送数据。"""
        if not self.is_connected:
            return False
        
        try:
            success = await self._do_send(data)
            if success:
                self._stats.message_sent += 1
            return success
        except Exception as e:
            self._stats.error_count += 1
            self._log_error(f"发送错误: {e}")
            return False
    
    def _start_background_tasks(self) -> None:
        """启动后台任务。"""
        self._receive_task = asyncio.create_task(self._receive_loop())
        if self._heartbeat_enabled:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
    
    async def _stop_background_tasks(self) -> None:
        """停止后台任务。"""
        tasks = []
        
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            tasks.append(self._receive_task)
        
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            tasks.append(self._heartbeat_task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _receive_loop(self) -> None:
        """接收消息循环。"""
        while self._running and self.is_connected:
            try:
                data = await self._do_receive()
                self._stats.message_received += 1
                self._stats.last_message_time = time.time()
                
                if self.on_message:
                    try:
                        if asyncio.iscoroutinefunction(self.on_message):
                            await self.on_message(data)
                        else:
                            self.on_message(data)
                    except Exception as e:
                        self._log_error(f"on_message 回调错误: {e}")
                
            except ConnectionError:
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._stats.error_count += 1
                self._log_error(f"接收错误: {e}")
        
        if self._running and self._reconnect_enabled:
            asyncio.create_task(self._handle_reconnect())
    
    async def _heartbeat_loop(self) -> None:
        """心跳循环。"""
        while self._running and self.is_connected:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                if self.is_connected:
                    await self._send_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._log_error(f"心跳错误: {e}")
    
    async def _send_heartbeat(self) -> None:
        """发送心跳（子类实现）。"""
        pass
    
    async def _handle_reconnect(self) -> None:
        """处理重连。"""
        await self._set_state(ConnectionState.RECONNECTING)
        await self.disconnect()
        await self.connect()
    
    def _log_info(self, message: str) -> None:
        """输出信息日志。"""
        from loguru import logger
        logger.info(f"[{self.name}] {message}")
    
    def _log_warning(self, message: str) -> None:
        """输出警告日志。"""
        from loguru import logger
        logger.warning(f"[{self.name}] {message}")
    
    def _log_error(self, message: str) -> None:
        """输出错误日志。"""
        from loguru import logger
        logger.error(f"[{self.name}] {message}")
