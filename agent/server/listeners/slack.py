#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :slack.py
# @Time      :2026/02/22
# @Author    :Ficus

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
    - signing_secret: 签名密钥（可选）

依赖:
    pip install slack-bolt

参考:
    - Slack API: https://api.slack.com/
    - Socket Mode: https://api.slack.com/apis/connections/socket
"""

import asyncio
import json
import time
from typing import Dict, Any, Optional

from loguru import logger

from ..base_listener import BaseListener
from ..message_bus import UnifiedMessage


class SlackListener(BaseListener):
    """
    Slack 监听器
    
    使用 Slack Bolt SDK 的 Socket Mode 实现消息接收。
    
    功能说明:
        - Socket Mode 长连接
        - 支持频道和私聊消息
        - 支持多种消息类型
        - 自动重连机制
    
    核心方法:
        - start: 启动监听器
        - stop: 停止监听器
        - send_message: 发送消息
        - _convert_to_unified: 转换消息格式
    
    配置示例:
        {
            "bot_token": "xoxb-xxxxxxxxxxxx-xxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxx",
            "app_token": "xapp-xxxxxxxxxxx-xxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            "signing_secret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        }
    """
    
    PLATFORM_NAME = "slack"
    PLATFORM_DISPLAY_NAME = "Slack"
    
    def __init__(self, name: str, config: Dict[str, Any], bus):
        """
        初始化 Slack 监听器。
        
        参数:
            name: 监听器名称
            config: 配置字典，包含 bot_token, app_token 等
            bus: 消息总线实例
        """
        super().__init__(name, config, bus)
        self._app = None
        self._bot_token = config.get("bot_token", "")
        self._app_token = config.get("app_token", "")
        self._signing_secret = config.get("signing_secret", "")
    
    async def start(self) -> bool:
        """
        启动 Slack 监听器。
        
        实现逻辑:
            1. 初始化 Slack Bolt App
            2. 配置 Socket Mode
            3. 注册消息处理器
            4. 订阅 outgoing 事件
        
        返回:
            bool: 启动是否成功
        """
        try:
            from slack_bolt.async_app import AsyncApp
            from slack_sdk.web.async_client import AsyncWebClient
            
            if not self._bot_token:
                logger.error(f"[{self.name}] 缺少 bot_token 配置")
                return False
            
            if not self._app_token:
                logger.error(f"[{self.name}] 缺少 app_token 配置（Socket Mode 需要）")
                return False
            
            logger.info(f"[{self.name}] 正在启动 Slack 监听器...")
            logger.info(f"[{self.name}] Bot Token: {self._bot_token[:20]}...")
            logger.info(f"[{self.name}] App Token: {self._app_token[:20]}...")
            
            # 初始化 Bolt App
            self._app = AsyncApp(
                token=self._bot_token,
                signing_secret=self._signing_secret or None
            )
            
            # 注册消息处理器
            @self._app.message()
            async def handle_message(message, say, client):
                """处理收到的消息"""
                logger.info(f"[{self.name}] 📨 收到消息")
                
                # 构造原始消息格式
                raw_data = {
                    "type": "message",
                    "channel": message.get("channel"),
                    "user": message.get("user"),
                    "text": message.get("text", ""),
                    "ts": message.get("ts"),
                    "thread_ts": message.get("thread_ts"),
                    "blocks": message.get("blocks", []),
                    "files": message.get("files", []),
                    "attachments": message.get("attachments", [])
                }
                
                # 发布到消息总线
                await self._publish_incoming(raw_data)
            
            # 在后台启动 Socket Mode
            self._create_task(self._start_socket_mode(), name="slack_socket")
            
            # 订阅 outgoing 事件
            self.bus.subscribe("outgoing", self._handle_outgoing)
            
            self._running = True
            
            logger.info(f"[{self.name}] ═════════════════════════════════════════")
            logger.info(f"[{self.name}] 🎉 Slack 监听器启动成功")
            logger.info(f"[{self.name}] 🔌 连接模式: Socket Mode")
            logger.info(f"[{self.name}] ═════════════════════════════════════════")
            
            return True
            
        except ImportError:
            logger.error(f"[{self.name}] 缺少依赖: slack-bolt, 请安装: pip install slack-bolt")
            return False
        except Exception as e:
            logger.error(f"[{self.name}] 启动失败: {e}")
            import traceback
            logger.error(f"[{self.name}] 错误堆栈:\n{traceback.format_exc()}")
            return False
    
    async def _start_socket_mode(self) -> None:
        """
        启动 Socket Mode 连接。
        """
        try:
            from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
            
            # 创建 Socket Mode Handler
            handler = AsyncSocketModeHandler(
                app=self._app,
                app_token=self._app_token
            )
            
            logger.info(f"[{self.name}] 正在启动 Socket Mode...")
            
            # 启动连接
            await handler.start_async()
            
            # 保持运行
            while self._running:
                await asyncio.sleep(1)
                
            # 停止连接
            await handler.close_async()
            
        except Exception as e:
            logger.error(f"[{self.name}] Socket Mode 错误: {e}")
            import traceback
            logger.error(f"[{self.name}] 错误详情:\n{traceback.format_exc()}")
    
    async def stop(self) -> None:
        """
        停止 Slack 监听器。
        """
        logger.info(f"[{self.name}] 正在停止...")
        self._running = False
        await super().stop()
        logger.info(f"[{self.name}] 已停止")
    
    async def send_message(self, unified_msg: UnifiedMessage) -> bool:
        """
        发送消息到 Slack。
        
        参数:
            unified_msg: 统一格式的消息
        
        返回:
            bool: 发送是否成功
        """
        if not self._app:
            logger.error(f"[{self.name}] App 未初始化")
            return False
        
        try:
            client = self._app.client
            
            # 解析 chat_id（格式: channel_id 或 channel_id|thread_ts）
            chat_parts = unified_msg.chat_id.split("|")
            channel = chat_parts[0]
            thread_ts = chat_parts[1] if len(chat_parts) > 1 else None
            
            kwargs = {
                "channel": channel,
                "text": unified_msg.content
            }
            
            if thread_ts:
                kwargs["thread_ts"] = thread_ts
            
            await client.chat_postMessage(**kwargs)
            
            logger.info(f"[{self.name}] 消息已发送")
            return True
            
        except Exception as e:
            logger.error(f"[{self.name}] 发送消息失败: {e}")
            return False
    
    async def _handle_outgoing(self, unified_msg: UnifiedMessage) -> None:
        """
        处理 outgoing 事件。
        
        参数:
            unified_msg: 统一格式的消息
        """
        if unified_msg.listener == self.name:
            await self.send_message(unified_msg)
    
    async def _convert_to_unified(self, raw: Dict[str, Any]) -> UnifiedMessage:
        """
        将 Slack 消息转换为统一格式。
        
        参数:
            raw: Slack 原始消息
        
        返回:
            UnifiedMessage: 统一格式的消息
        """
        # 提取消息内容
        content = raw.get("text", "")
        
        # 处理文件
        files = raw.get("files", [])
        if files:
            file_names = [f.get("name", "文件") for f in files]
            content += f"\n[附件: {', '.join(file_names)}]"
        
        # 处理区块
        blocks = raw.get("blocks", [])
        if blocks and not content:
            for block in blocks:
                if block.get("type") == "section":
                    text_obj = block.get("text", {})
                    if text_obj.get("type") == "mrkdwn":
                        content += text_obj.get("text", "")
        
        # 构造 chat_id
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
