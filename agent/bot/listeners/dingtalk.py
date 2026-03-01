#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :dingtalk.py
# @Time      :2026/02/22
# @Author    :Ficus

"""
钉钉监听器模块（简化版）

功能说明:
    - 使用钉钉官方 Stream 模式长连接
    - 支持接收和发送消息
    - 将钉钉消息转换为统一格式

配置项:
    - app_key: 应用 AppKey
    - app_secret: 应用 AppSecret

依赖:
    pip install websockets requests

参考:
    - 钉钉开放平台: https://open.dingtalk.com/document/
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
    """
    钉钉监听器
    
    使用钉钉 Stream 模式实现消息接收，基于统一连接架构。
    
    配置示例:
        {
            "app_key": "dingxxxxxxxxxxxxxxxx",
            "app_secret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        }
    """
    
    PLATFORM_NAME = "dingtalk"
    PLATFORM_DISPLAY_NAME = "钉钉"
    
    def __init__(self, name: str, config: Dict[str, Any], bus):
        super().__init__(name, config, bus)
        self._app_key = config.get("app_key", "")
        self._app_secret = config.get("app_secret", "")
        self._access_token = None
        self._connection = None
    
    async def start(self) -> bool:
        """启动钉钉监听器。"""
        if not all([self._app_key, self._app_secret]):
            logger.error(f"[{self.name}] 缺少配置: app_key, app_secret")
            return False
        
        try:
            logger.info(f"[{self.name}] 正在启动钉钉监听器...")
            
            # 获取 access_token
            if not await self._refresh_token():
                return False
            
            # 创建 WebSocket 连接（钉钉 Stream）
            ws_url = f"wss://comet.dingtalk.com/comet_server?token={self._access_token}"
            self._connection = WebSocketConnection(
                url=ws_url,
                name=f"{self.name}_stream",
                reconnect_interval=5,
                heartbeat_interval=30
            )
            
            # 设置回调
            self._connection.on_message = self._handle_message
            self._connection.on_connect = lambda: logger.info(f"[{self.name}] ✅ Stream 已连接")
            
            # 启动连接
            success = await self._connection.connect()
            if not success:
                return False
            
            # 订阅 outgoing 事件
            self.bus.subscribe("outgoing", self._handle_outgoing)
            
            self._running = True
            
            logger.info(f"[{self.name}] ═════════════════════════════════════════")
            logger.info(f"[{self.name}] 🎉 钉钉监听器启动成功")
            logger.info(f"[{self.name}] 🔌 连接模式: Stream 长连接")
            logger.info(f"[{self.name}] ═════════════════════════════════════════")
            
            return True
            
        except Exception as e:
            logger.error(f"[{self.name}] 启动失败: {e}")
            return False
    
    async def _refresh_token(self) -> bool:
        """刷新 access_token。"""
        try:
            import requests
            
            url = "https://oapi.dingtalk.com/gettoken"
            params = {"appkey": self._app_key, "appsecret": self._app_secret}
            
            response = await asyncio.to_thread(requests.get, url, params=params, timeout=30)
            data = response.json()
            
            if data.get("errcode") == 0:
                self._access_token = data.get("access_token")
                logger.info(f"[{self.name}] Token 刷新成功")
                return True
            else:
                logger.error(f"[{self.name}] 获取 token 失败: {data}")
                return False
                
        except Exception as e:
            logger.error(f"[{self.name}] 刷新 token 失败: {e}")
            return False
    
    async def _handle_message(self, data) -> None:
        """处理收到的消息。"""
        try:
            if isinstance(data, str):
                data = json.loads(data)
            
            # 处理心跳
            if data.get("type") == "heartbeat":
                return
            
            logger.info(f"[{self.name}] 📨 收到消息")
            await self._publish_incoming(data)
            
        except Exception as e:
            logger.error(f"[{self.name}] 处理消息失败: {e}")
    
    async def stop(self) -> bool:
        """停止监听器。"""
        self._running = False
        if self._connection:
            await self._connection.disconnect()
        await super().stop()
        return True
    
    async def send_message(self, target: Dict[str, str], content: str, **kwargs) -> Dict[str, Any]:
        """发送消息。"""
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
                logger.info(f"[{self.name}] 消息发送成功")
                return {"success": True}
            else:
                logger.error(f"[{self.name}] 发送失败: {result}")
                return {"success": False, "error": str(result)}
                
        except Exception as e:
            logger.error(f"[{self.name}] 发送消息失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def _handle_outgoing(self, data: dict) -> None:
        """处理 outgoing 事件。"""
        if data.get("listener") != self.name:
            return
        
        target = {"chat_id": data.get("chat_id")}
        await self.send_message(target, data.get("content", ""))
    
    async def _convert_to_unified(self, raw: Dict[str, Any]) -> UnifiedMessage:
        """转换为统一格式。"""
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
