#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
QQ 监听器模块（使用统一连接架构）

功能说明:
    - 使用 WebSocket 连接到 go-cqhttp 或 OneBot 协议实现
    - 基于统一连接管理架构，简化实现
    - 支持接收和发送消息

配置项:
    - ws_url: WebSocket 连接地址
    - access_token: 访问令牌（可选）

依赖:
    pip install websockets
"""

import json
import time
from typing import Dict, Any

from loguru import logger

from ..base_listener import BaseListener
from ..message_bus import UnifiedMessage
from ..connection import WebSocketConnection


class QQListener(BaseListener):
    """QQ 监听器"""
    
    PLATFORM_NAME = "qq"
    PLATFORM_DISPLAY_NAME = "QQ"
    
    def __init__(self, name: str, config: Dict[str, Any], bus):
        super().__init__(name, config, bus)
        self._ws_url = config.get("ws_url", "")
        self._access_token = config.get("access_token", "")
        self._connection: WebSocketConnection = None
    
    async def start(self) -> bool:
        if not self._ws_url:
            logger.error(f"[{self.name}] 缺少 ws_url 配置")
            return False
        
        try:
            self._connection = WebSocketConnection(
                url=self._ws_url,
                name=f"{self.name}_ws",
                access_token=self._access_token,
                heartbeat_interval=30,
                reconnect_interval=5,
                reconnect_enabled=True
            )
            
            self._connection.on_message = self._handle_ws_message
            self._connection.on_connect = lambda: logger.info(f"[{self.name}] ✅ WebSocket 已连接")
            self._connection.on_disconnect = lambda: logger.warning(f"[{self.name}] 🔌 WebSocket 已断开")
            
            success = await self._connection.connect()
            if not success:
                return False
            
            self.bus.subscribe("outgoing", self._handle_outgoing)
            
            self._running = True
            
            logger.info(f"[{self.name}] 🎉 QQ 监听器启动成功")
            
            return True
            
        except Exception as e:
            logger.error(f"[{self.name}] 启动失败: {e}")
            return False
    
    async def stop(self) -> bool:
        self._running = False
        
        if self._connection:
            await self._connection.disconnect()
            self._connection = None
        
        await self._cancel_all_tasks()
        
        logger.info(f"[{self.name}] 已停止")
        return True
    
    async def _handle_ws_message(self, data) -> None:
        try:
            if isinstance(data, str):
                data = json.loads(data)
            
            if data.get("post_type") == "meta_event":
                return
            
            if data.get("post_type") == "message":
                await self._publish_incoming(data)
                
        except json.JSONDecodeError:
            pass
        except Exception as e:
            logger.error(f"[{self.name}] 处理消息失败: {e}")
    
    async def send_message(self, target: Dict[str, str], content: str, **kwargs) -> Dict[str, Any]:
        if not self._connection or not self._connection.is_connected:
            return {"success": False, "error": "WebSocket 未连接"}
        
        try:
            chat_id = target.get("chat_id", "")
            
            if chat_id.startswith("group_"):
                group_id = chat_id.replace("group_", "")
                msg = {
                    "action": "send_group_msg",
                    "params": {
                        "group_id": int(group_id),
                        "message": content
                    }
                }
            else:
                msg = {
                    "action": "send_private_msg",
                    "params": {
                        "user_id": int(chat_id),
                        "message": content
                    }
                }
            
            success = await self._connection.send(msg)
            return {"success": success}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _convert_to_unified(self, raw: Dict[str, Any]) -> UnifiedMessage:
        message_type = raw.get("message_type", "")
        
        if message_type == "private":
            chat_id = str(raw.get("user_id", ""))
        elif message_type == "group":
            chat_id = f"group_{raw.get('group_id', '')}"
        else:
            chat_id = ""
        
        messages = raw.get("message", [])
        content = ""
        
        if isinstance(messages, list):
            for msg in messages:
                if msg.get("type") == "text":
                    content += msg.get("data", {}).get("text", "")
                elif msg.get("type") == "image":
                    content += "[图片]"
        elif isinstance(messages, str):
            content = messages
        
        return UnifiedMessage(
            id=str(raw.get("message_id", "")),
            listener=self.name,
            platform=self.PLATFORM_NAME,
            type=message_type,
            content=content,
            user_id=str(raw.get("user_id", "")),
            chat_id=chat_id,
            thread_id=None,
            timestamp=raw.get("time", int(time.time())),
            raw=raw
        )
