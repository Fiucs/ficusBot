#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
Slack 监听器模块

功能说明:
    - 使用 Slack Bolt SDK
    - 支持 Socket Mode 长连接接收消息
    - 支持发送文本、区块、附件等消息
    - 将 Slack 消息转换为统一格式

配置项:
    - bot_token: Bot User OAuth Token (xoxb-...)
    - app_token: App-Level Token (xapp-...)

依赖:
    pip install slack-bolt
"""

import asyncio
import json
import time
from typing import Dict, Any, Optional

from loguru import logger

from ..base_listener import BaseListener
from ..message_bus import UnifiedMessage


class SlackListener(BaseListener):
    """Slack 监听器"""
    
    PLATFORM_NAME = "slack"
    PLATFORM_DISPLAY_NAME = "Slack"
    
    def __init__(self, name: str, config: Dict[str, Any], bus):
        super().__init__(name, config, bus)
        self._app = None
        self._bot_token = config.get("bot_token", "")
        self._app_token = config.get("app_token", "")
        self._signing_secret = config.get("signing_secret", "")
    
    async def start(self) -> bool:
        try:
            from slack_bolt.async_app import AsyncApp
            
            if not self._bot_token:
                logger.error(f"[{self.name}] 缺少 bot_token 配置")
                return False
            
            if not self._app_token:
                logger.error(f"[{self.name}] 缺少 app_token 配置（Socket Mode 需要）")
                return False
            
            self._app = AsyncApp(
                token=self._bot_token,
                signing_secret=self._signing_secret or None
            )
            
            @self._app.message()
            async def handle_message(message, say, client):
                raw_data = {
                    "type": "message",
                    "channel": message.get("channel"),
                    "user": message.get("user"),
                    "text": message.get("text", ""),
                    "ts": message.get("ts"),
                    "thread_ts": message.get("thread_ts"),
                    "blocks": message.get("blocks", []),
                    "files": message.get("files", []),
                }
                
                await self._publish_incoming(raw_data)
            
            self._create_task(self._start_socket_mode(), name="slack_socket")
            
            self.bus.subscribe("outgoing", self._handle_outgoing)
            
            self._running = True
            
            logger.info(f"[{self.name}] 🎉 Slack 监听器启动成功")
            
            return True
            
        except ImportError:
            logger.error(f"[{self.name}] 缺少依赖: slack-bolt, 请安装: pip install slack-bolt")
            return False
        except Exception as e:
            logger.error(f"[{self.name}] 启动失败: {e}")
            return False
    
    async def _start_socket_mode(self) -> None:
        try:
            from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
            
            handler = AsyncSocketModeHandler(
                app=self._app,
                app_token=self._app_token
            )
            
            await handler.start_async()
            
            while self._running:
                await asyncio.sleep(1)
            
            await handler.close_async()
            
        except Exception as e:
            logger.error(f"[{self.name}] Socket Mode 错误: {e}")
    
    async def stop(self) -> bool:
        self._running = False
        await self._cancel_all_tasks()
        logger.info(f"[{self.name}] 已停止")
        return True
    
    async def send_message(self, target: Dict[str, str], content: str, **kwargs) -> Dict[str, Any]:
        if not self._app:
            return {"success": False, "error": "App 未初始化"}
        
        try:
            client = self._app.client
            
            chat_id = target.get("chat_id", "")
            chat_parts = chat_id.split("|")
            channel = chat_parts[0]
            thread_ts = chat_parts[1] if len(chat_parts) > 1 else None
            
            msg_kwargs = {
                "channel": channel,
                "text": content
            }
            
            if thread_ts:
                msg_kwargs["thread_ts"] = thread_ts
            
            await client.chat_postMessage(**msg_kwargs)
            
            return {"success": True}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _convert_to_unified(self, raw: Dict[str, Any]) -> UnifiedMessage:
        content = raw.get("text", "")
        
        files = raw.get("files", [])
        if files:
            file_names = [f.get("name", "文件") for f in files]
            content += f"\n[附件: {', '.join(file_names)}]"
        
        blocks = raw.get("blocks", [])
        if blocks and not content:
            for block in blocks:
                if block.get("type") == "section":
                    text_obj = block.get("text", {})
                    if text_obj.get("type") == "mrkdwn":
                        content += text_obj.get("text", "")
        
        channel = raw.get("channel", "")
        thread_ts = raw.get("thread_ts")
        chat_id = f"{channel}|{thread_ts}" if thread_ts else channel
        
        return UnifiedMessage(
            id=raw.get("ts", ""),
            listener=self.name,
            platform=self.PLATFORM_NAME,
            type="message",
            content=content,
            user_id=raw.get("user", ""),
            chat_id=chat_id,
            thread_id=thread_ts,
            timestamp=float(raw.get("ts", "0").split(".")[0]) if raw.get("ts") else time.time(),
            raw=raw
        )
