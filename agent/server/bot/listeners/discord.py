#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
Discord 监听器模块

功能说明:
    - 使用官方 SDK discord.py 实现
    - 支持 Gateway 模式接收消息
    - 支持消息内容和成员意图
    - 将 Discord 消息转换为统一格式

配置项:
    - token: Bot Token

依赖:
    pip install discord.py
"""

import asyncio
import time
from typing import Dict, Any, Optional

from loguru import logger

from ..base_listener import BaseListener
from ..message_bus import UnifiedMessage


class DiscordListener(BaseListener):
    """Discord 监听器"""
    
    PLATFORM_NAME = "discord"
    PLATFORM_DISPLAY_NAME = "Discord"
    
    def __init__(self, name: str, config: Dict[str, Any], bus):
        super().__init__(name, config, bus)
        self._bot = None
    
    async def start(self) -> bool:
        try:
            import discord
            from discord.ext import commands
            
            token = self.config.get("token")
            if not token:
                logger.error(f"[{self.name}] 缺少 token 配置")
                return False
            
            intents = discord.Intents.default()
            intents.message_content = True
            intents.members = True
            
            self._bot = commands.Bot(
                command_prefix="!",
                intents=intents,
                self_bot=False
            )
            
            @self._bot.event
            async def on_ready():
                self._bot_info = {
                    "id": str(self._bot.user.id),
                    "username": self._bot.user.name,
                    "discriminator": self._bot.user.discriminator
                }
                logger.info(f"[{self.name}] Discord Bot 已连接: {self._bot.user.name}")
            
            @self._bot.event
            async def on_message(message):
                if message.author.bot:
                    return
                await self._publish_incoming(message)
            
            self.bus.subscribe("outgoing", self._handle_outgoing)
            
            self._running = True
            
            self._create_task(self._run_bot(), f"{self.name}_gateway")
            
            logger.info(f"[{self.name}] Discord 监听器已启动")
            return True
            
        except ImportError as e:
            logger.error(f"[{self.name}] 缺少依赖: {e}, 请安装: pip install discord.py")
            return False
        except Exception as e:
            logger.error(f"[{self.name}] 启动失败: {e}")
            return False
    
    async def _run_bot(self) -> None:
        try:
            await self._bot.start(self.config["token"])
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[{self.name}] Bot 运行异常: {e}")
    
    async def stop(self) -> bool:
        self._running = False
        
        if self._bot:
            await self._bot.close()
        
        await self._cancel_all_tasks()
        
        logger.info(f"[{self.name}] Discord 监听器已停止")
        return True
    
    async def send_message(self, target: Dict[str, str], content: str, **kwargs) -> Dict[str, Any]:
        try:
            chat_id = target.get("chat_id")
            if not chat_id:
                return {"success": False, "error": "缺少 chat_id"}
            
            channel = self._bot.get_channel(int(chat_id))
            if not channel:
                return {"success": False, "error": f"找不到频道: {chat_id}"}
            
            reply_to = kwargs.get("reply_to")
            
            if reply_to:
                try:
                    reference = await channel.fetch_message(int(reply_to))
                    message = await channel.send(content, reference=reference)
                except:
                    message = await channel.send(content)
            else:
                message = await channel.send(content)
            
            return {"success": True, "message_id": str(message.id)}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _convert_to_unified(self, raw) -> UnifiedMessage:
        message_type = "text"
        content = raw.content or ""
        images = []
        
        if raw.attachments:
            for attachment in raw.attachments:
                if attachment.content_type and attachment.content_type.startswith("image/"):
                    message_type = "image"
                    images.append(attachment.url)
                else:
                    message_type = "file"
                    content = f"{content}\n[附件: {attachment.filename}]".strip()
        
        thread_id = str(raw.thread.id) if raw.thread else None
        
        return UnifiedMessage(
            id=str(raw.id),
            listener=self.name,
            platform=self.PLATFORM_NAME,
            type=message_type,
            content=content,
            images=images,
            user_id=str(raw.author.id),
            chat_id=str(raw.channel.id),
            thread_id=thread_id,
            timestamp=raw.created_at.timestamp() if raw.created_at else time.time(),
            raw=None
        )
