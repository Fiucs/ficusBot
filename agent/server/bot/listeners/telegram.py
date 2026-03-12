#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
Telegram 监听器模块

功能说明:
    - 使用官方 SDK python-telegram-bot 实现
    - 支持长轮询模式接收消息
    - 支持代理配置
    - 将 Telegram 消息转换为统一格式

配置项:
    - token: Bot Token
    - proxy: 代理地址（可选）

依赖:
    pip install python-telegram-bot
"""

import asyncio
import time
from typing import Dict, Any, Optional

from loguru import logger

from ..base_listener import BaseListener
from ..message_bus import UnifiedMessage


class TelegramListener(BaseListener):
    """
    Telegram 监听器
    
    使用 python-telegram-bot 官方推荐库实现。
    """
    
    PLATFORM_NAME = "telegram"
    PLATFORM_DISPLAY_NAME = "Telegram"
    
    def __init__(self, name: str, config: Dict[str, Any], bus):
        super().__init__(name, config, bus)
        self._app = None
        self._bot = None
    
    async def start(self) -> bool:
        try:
            from telegram import Bot
            from telegram.ext import Application, MessageHandler, filters
            
            token = self.config.get("token")
            if not token:
                logger.error(f"[{self.name}] 缺少 token 配置")
                return False
            
            builder = Application.builder().token(token)
            
            proxy = self.config.get("proxy")
            if proxy:
                from telegram.request import HTTPXRequest
                request = HTTPXRequest(proxy=proxy)
                builder = builder.request(request).get_updates_request(request)
                logger.info(f"[{self.name}] 使用代理: {proxy}")
            
            self._app = builder.build()
            
            self._app.add_handler(
                MessageHandler(filters.ALL, self._handle_update)
            )
            
            self.bus.subscribe("outgoing", self._handle_outgoing)
            
            await self._app.initialize()
            await self._app.start()
            
            self._bot = self._app.bot
            
            self._bot_info = {
                "id": (await self._bot.get_me()).id,
                "username": (await self._bot.get_me()).username,
                "name": (await self._bot.get_me()).first_name
            }
            
            self._running = True
            
            self._create_task(self._polling(), f"{self.name}_polling")
            
            logger.info(
                f"[{self.name}] Telegram 监听器已启动, "
                f"bot: @{self._bot_info.get('username')}"
            )
            return True
            
        except ImportError as e:
            logger.error(f"[{self.name}] 缺少依赖: {e}, 请安装: pip install python-telegram-bot")
            return False
        except Exception as e:
            logger.error(f"[{self.name}] 启动失败: {e}")
            return False
    
    async def _polling(self) -> None:
        try:
            await self._app.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=["message", "edited_message", "callback_query"]
            )
            
            while self._running:
                await asyncio.sleep(1)
                
        except asyncio.CancelledError:
            logger.debug(f"[{self.name}] 轮询任务被取消")
        except Exception as e:
            logger.error(f"[{self.name}] 轮询异常: {e}")
    
    async def stop(self) -> bool:
        try:
            self._running = False
            
            if self._app:
                if self._app.updater and self._app.updater.running:
                    await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
            
            await self._cancel_all_tasks()
            
            logger.info(f"[{self.name}] Telegram 监听器已停止")
            return True
            
        except Exception as e:
            logger.error(f"[{self.name}] 停止失败: {e}")
            return False
    
    async def _handle_update(self, update, context) -> None:
        if update.message:
            await self._publish_incoming(update)
        elif update.edited_message:
            update.message = update.edited_message
            await self._publish_incoming(update)
        elif update.callback_query:
            await self._handle_callback_query(update.callback_query)
    
    async def _handle_callback_query(self, callback_query) -> None:
        from telegram import Update
        
        fake_update = Update(
            update_id=callback_query.id,
            message=callback_query.message
        )
        if callback_query.message:
            fake_update.message.text = f"[callback] {callback_query.data}"
            await self._publish_incoming(fake_update)
    
    async def send_message(self, target: Dict[str, str], content: str, **kwargs) -> Dict[str, Any]:
        try:
            chat_id = target.get("chat_id")
            if not chat_id:
                return {"success": False, "error": "缺少 chat_id"}
            
            parse_mode = kwargs.get("parse_mode", "Markdown")
            reply_to = kwargs.get("reply_to")
            
            message = await self._bot.send_message(
                chat_id=chat_id,
                text=content,
                parse_mode=parse_mode,
                reply_to_message_id=reply_to
            )
            
            return {
                "success": True,
                "message_id": str(message.message_id)
            }
            
        except Exception as e:
            logger.error(f"[{self.name}] 发送消息失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def _convert_to_unified(self, raw) -> UnifiedMessage:
        msg = raw.effective_message
        
        message_type = "text"
        content = ""
        images = []
        
        if msg.text:
            message_type = "text"
            content = msg.text
        elif msg.photo:
            message_type = "image"
            content = msg.caption or ""
            if msg.photo:
                largest_photo = msg.photo[-1]
                try:
                    file = await self._bot.get_file(largest_photo.file_id)
                    import base64
                    import io
                    photo_bytes = io.BytesIO()
                    await file.download_to_memory(photo_bytes)
                    photo_base64 = base64.b64encode(photo_bytes.getvalue()).decode('utf-8')
                    images.append(f"data:image/jpeg;base64,{photo_base64}")
                    logger.info(f"[{self.name}] 已下载图片，大小: {len(photo_bytes.getvalue())} bytes")
                except Exception as e:
                    logger.error(f"[{self.name}] 下载图片失败: {e}")
                    content = f"{content}\n[图片下载失败]".strip()
        elif msg.document:
            message_type = "file"
            content = msg.document.file_name or ""
        elif msg.sticker:
            message_type = "sticker"
            content = msg.sticker.emoji or ""
        elif msg.voice:
            message_type = "voice"
            content = "[语音消息]"
        else:
            message_type = "other"
            content = "[非文本消息]"
        
        thread_id = None
        if msg.is_topic_message:
            thread_id = str(msg.message_thread_id)
        
        return UnifiedMessage(
            id=str(msg.message_id),
            listener=self.name,
            platform=self.PLATFORM_NAME,
            type=message_type,
            content=content,
            images=images,
            user_id=str(msg.from_user.id) if msg.from_user else "",
            chat_id=str(msg.chat_id),
            thread_id=thread_id,
            timestamp=msg.date.timestamp() if msg.date else time.time(),
            raw=raw.to_dict() if hasattr(raw, 'to_dict') else None
        )
