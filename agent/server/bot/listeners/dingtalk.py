#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
钉钉监听器模块

功能说明:
    - 使用钉钉官方 Stream 模式长连接
    - 支持接收和发送消息
    - 将钉钉消息转换为统一格式

配置项:
    - app_key: 应用 AppKey
    - app_secret: 应用 AppSecret

依赖:
    pip install websockets requests
"""

import asyncio
import json
import time
from typing import Dict, Any

from loguru import logger

from ..base_listener import BaseListener
from ..message_bus import UnifiedMessage
from ..connection import WebSocketConnection


class DingTalkListener(BaseListener):
    """钉钉监听器"""
    
    PLATFORM_NAME = "dingtalk"
    PLATFORM_DISPLAY_NAME = "钉钉"
    
    def __init__(self, name: str, config: Dict[str, Any], bus):
        super().__init__(name, config, bus)
        self._app_key = config.get("app_key", "")
        self._app_secret = config.get("app_secret", "")
        self._access_token = None
        self._connection = None
    
    async def start(self) -> bool:
        if not all([self._app_key, self._app_secret]):
            logger.error(f"[{self.name}] 缺少配置: app_key, app_secret")
            return False
        
        try:
            if not await self._refresh_token():
                return False
            
            ws_url = f"wss://comet.dingtalk.com/comet_server?token={self._access_token}"
            self._connection = WebSocketConnection(
                url=ws_url,
                name=f"{self.name}_stream",
                reconnect_interval=5,
                heartbeat_interval=30
            )
            
            self._connection.on_message = self._handle_message
            self._connection.on_connect = lambda: logger.info(f"[{self.name}] ✅ Stream 已连接")
            
            success = await self._connection.connect()
            if not success:
                return False
            
            self.bus.subscribe("outgoing", self._handle_outgoing)
            
            self._running = True
            
            logger.info(f"[{self.name}] 🎉 钉钉监听器启动成功")
            
            return True
            
        except Exception as e:
            logger.error(f"[{self.name}] 启动失败: {e}")
            return False
    
    async def _refresh_token(self) -> bool:
        try:
            import requests
            
            url = "https://oapi.dingtalk.com/gettoken"
            params = {"appkey": self._app_key, "appsecret": self._app_secret}
            
            response = await asyncio.to_thread(requests.get, url, params=params, timeout=30)
            data = response.json()
            
            if data.get("errcode") == 0:
                self._access_token = data.get("access_token")
                return True
            else:
                logger.error(f"[{self.name}] 获取 token 失败: {data}")
                return False
                
        except Exception as e:
            logger.error(f"[{self.name}] 刷新 token 失败: {e}")
            return False
    
    async def _handle_message(self, data) -> None:
        try:
            if isinstance(data, str):
                data = json.loads(data)
            
            if data.get("type") == "heartbeat":
                return
            
            await self._publish_incoming(data)
            
        except Exception as e:
            logger.error(f"[{self.name}] 处理消息失败: {e}")
    
    async def stop(self) -> bool:
        self._running = False
        if self._connection:
            await self._connection.disconnect()
        await self._cancel_all_tasks()
        return True
    
    async def send_message(self, target: Dict[str, str], content: str, **kwargs) -> Dict[str, Any]:
        try:
            import requests
            
            url = f"https://oapi.dingtalk.com/message/send_to_conversation?access_token={self._access_token}"
            
            payload = {
                "receiver": {"staffId": target.get("chat_id", "")},
                "msg": {
                    "msgtype": "text",
                    "text": {"content": content}
                }
            }
            
            response = await asyncio.to_thread(
                requests.post, url, json=payload, timeout=30
            )
            result = response.json()
            
            if result.get("errcode") == 0:
                return {"success": True}
            else:
                return {"success": False, "error": str(result)}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _convert_to_unified(self, raw: Dict[str, Any]) -> UnifiedMessage:
        data = raw.get("data", {})
        sender = data.get("senderStaffId", "")
        
        return UnifiedMessage(
            id=str(data.get("messageId", "")),
            listener=self.name,
            platform=self.PLATFORM_NAME,
            type="text",
            content=data.get("content", ""),
            user_id=sender,
            chat_id=data.get("conversationId", ""),
            thread_id=None,
            timestamp=time.time(),
            raw=raw
        )
