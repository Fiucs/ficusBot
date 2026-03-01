#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :discord.py
# @Time      :2026/02/22
# @Author    :Ficus

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
    """
    Discord 监听器
    
    使用 discord.py 官方推荐库实现。
    
    功能说明:
        - 支持 Gateway 模式接收消息
        - 支持消息内容和成员意图
        - 自动处理消息转换
    
    核心方法:
        - start: 启动监听器
        - stop: 停止监听器
        - send_message: 发送消息
        - _convert_to_unified: 转换消息格式
    
    配置示例:
        {
            "token": "YOUR_BOT_TOKEN"
        }
    """
    
    PLATFORM_NAME = "discord"
    PLATFORM_DISPLAY_NAME = "Discord"
    
    def __init__(self, name: str, config: Dict[str, Any], bus):
        """
        初始化 Discord 监听器。
        
        参数:
            name: 监听器名称
            config: 配置字典，包含 token
            bus: 消息总线实例
        """
        super().__init__(name, config, bus)
        self._bot = None
    
    async def start(self) -> bool:
        """
        启动 Discord 监听器。
        
        实现逻辑:
            1. 初始化 discord.py Bot
            2. 配置消息处理器
            3. 订阅 outgoing 事件
            4. 启动 Gateway 连接
        
        返回:
            bool: 启动是否成功
        """
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
                logger.info(
                    f"[{self.name}] Discord Bot 已连接: "
                    f"{self._bot.user.name}#{self._bot.user.discriminator}"
                )
            
            @self._bot.event
            async def on_message(message):
                if message.author.bot:
                    return
                
                await self._publish_incoming(message)
            
            @self._bot.event
            async def on_error(event, *args, **kwargs):
                logger.error(f"[{self.name}] Discord 事件错误: {event}")
            
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
        """运行 Discord Bot"""
        try:
            await self._bot.start(self.config["token"])
        except asyncio.CancelledError:
            logger.debug(f"[{self.name}] Bot 任务被取消")
        except Exception as e:
            logger.error(f"[{self.name}] Bot 运行异常: {e}")
    
    async def stop(self) -> bool:
        """
        停止 Discord 监听器。
        
        返回:
            bool: 停止是否成功
        """
        try:
            self._running = False
            
            if self._bot:
                await self._bot.close()
            
            await self._cancel_all_tasks()
            
            logger.info(f"[{self.name}] Discord 监听器已停止")
            return True
            
        except Exception as e:
            logger.error(f"[{self.name}] 停止失败: {e}")
            return False
    
    async def send_message(self, target: Dict[str, str], content: str, **kwargs) -> Dict[str, Any]:
        """
        发送消息到 Discord。
        
        参数:
            target: 目标信息，包含 chat_id（频道ID）
            content: 消息内容
            **kwargs: 其他参数（如 reply_to）
        
        返回:
            Dict: 发送结果
        """
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
            
            return {
                "success": True,
                "message_id": str(message.id)
            }
            
        except Exception as e:
            logger.error(f"[{self.name}] 发送消息失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def _convert_to_unified(self, raw) -> UnifiedMessage:
        """
        将 Discord 消息转换为统一格式。
        
        参数:
            raw: discord.Message 对象
        
        返回:
            UnifiedMessage: 统一格式消息
        """
        message_type = "text"
        content = raw.content or ""
        
        if raw.attachments:
            if len(raw.attachments) == 1:
                attachment = raw.attachments[0]
                if attachment.content_type and attachment.content_type.startswith("image/"):
                    message_type = "image"
                else:
                    message_type = "file"
                content = f"{content}\n[附件: {attachment.filename}]".strip()
            else:
                message_type = "file"
                files = ", ".join(a.filename for a in raw.attachments)
                content = f"{content}\n[附件: {files}]".strip()
        
        if raw.embeds:
            embed = raw.embeds[0]
            if embed.description:
                content = f"{content}\n{embed.description}".strip()
        
        thread_id = str(raw.thread.id) if raw.thread else None
        
        return UnifiedMessage(
            id=str(raw.id),
            listener=self.name,
            platform=self.PLATFORM_NAME,
            type=message_type,
            content=content,
            user_id=str(raw.author.id),
            chat_id=str(raw.channel.id),
            thread_id=thread_id,
            timestamp=raw.created_at.timestamp() if raw.created_at else time.time(),
            raw=None
        )
