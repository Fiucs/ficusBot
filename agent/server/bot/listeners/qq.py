#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
QQ 监听器模块（使用 qq-botpy 官方 SDK）

功能说明:
    - 使用 qq-botpy 官方 SDK 实现 WebSocket 消息收发
    - 支持频道消息、群聊消息、私聊消息
    - 支持文本、图片、Markdown、Embed 消息发送
    - 支持图片下载、本地保存、base64 转换

配置项:
    - appid: 机器人 AppID
    - secret: 机器人 AppSecret (token)
    - image_save_dir: 图片保存目录（可选）

依赖:
    pip install qq-botpy aiohttp
"""


import base64
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp
import botpy
from botpy import logging as botpy_logging
from botpy.message import DirectMessage, GroupMessage, Message
from loguru import logger

from ..base_listener import BaseListener
from ..message_bus import UnifiedMessage


class QQListener(BaseListener):
    """
    QQ 监听器（官方 SDK 版本）

    功能说明:
        - 基于 qq-botpy 官方 SDK 实现
        - 支持 WebSocket 长连接模式接收消息
        - 支持频道、群聊、私聊三种场景
        - 支持文本、图片（URL/base64）、Markdown、Embed 消息发送
        - 支持图片下载、本地保存、base64 转换
        - 支持文件发送（仅 C2C 单聊）

    核心方法:
        - start: 启动监听器
        - stop: 停止监听器
        - send_message: 发送消息
        - send_text: 发送文本消息
        - send_image: 发送图片消息
        - send_video: 发送视频消息
        - send_voice: 发送语音消息
        - send_file: 发送文件消息（仅 C2C）
        - send_markdown: 发送 Markdown 消息
        - send_embed: 发送 Embed 消息

    配置项:
        - appid: 机器人 AppID
        - secret: 机器人 AppSecret
        - image_save_dir: 图片保存目录
    """

    PLATFORM_NAME = "qq"
    PLATFORM_DISPLAY_NAME = "QQ"

    def __init__(self, name: str, config: Dict[str, Any], bus):
        super().__init__(name, config, bus)
        self._appid = config.get("appid", "")
        self._secret = config.get("secret", "")
        self._image_save_dir = config.get(
            "image_save_dir",
            os.path.join(os.path.dirname(__file__), "downloaded_images")
        )
        self._client: Optional["_BotpyClientWrapper"] = None
        self._intents: Optional[botpy.Intents] = None
        self._api = None
        self._log = botpy_logging.get_logger()

    async def start(self) -> bool:
        if not self._appid or not self._secret:
            logger.error(f"[{self.name}] 缺少 appid 或 secret 配置")
            return False

        try:
            self._init_intents()

            self._client = _BotpyClientWrapper(
                intents=self._intents,
                listener=self
            )

            logger.info(f"[{self.name}] 🚀 QQ 监听器启动中...")
            logger.info(f"[{self.name}] AppID: {self._appid[:8]}...")

            self.bus.subscribe("outgoing", self._handle_outgoing)

            self._running = True

            self._create_task(
                self._run_botpy_client(),
                name=f"{self.name}_botpy_client"
            )

            logger.info(f"[{self.name}] 🎉 QQ 监听器启动成功")
            return True

        except Exception as e:
            logger.error(f"[{self.name}] 启动失败: {e}")
            return False

    async def _run_botpy_client(self):
        try:
            await self._client.start(appid=self._appid, secret=self._secret)
        except Exception as e:
            logger.error(f"[{self.name}] botpy 客户端运行异常: {e}")
            self._running = False

    def _init_intents(self):
        self._intents = botpy.Intents.none()
        self._intents.public_guild_messages = True
        self._intents.direct_message = True
        self._intents.public_messages = True

    async def stop(self) -> bool:
        self._running = False

        if self._client:
            try:
                if hasattr(self._client, 'close'):
                    await self._client.close()
                elif hasattr(self._client, '_close'):
                    self._client._close()
                else:
                    logger.debug(f"[{self.name}] botpy 客户端无 close 方法，跳过")
            except Exception as e:
                logger.warning(f"[{self.name}] 关闭 botpy 客户端异常: {e}")
            self._client = None

        await self._cancel_all_tasks()

        logger.info(f"[{self.name}] 已停止")
        return True

    async def send_message(self, target: Dict[str, str], content: str, **kwargs) -> Dict[str, Any]:
        if not self._client or not self._client.api:
            return {"success": False, "error": "botpy 客户端未初始化"}

        try:
            chat_id = target.get("chat_id", "")
            msg_type = kwargs.get("msg_type", 0)
            msg_id = kwargs.get("msg_id", "")
            msg_seq = kwargs.get("msg_seq", 1)
            images = kwargs.get("images", [])
            markdown = kwargs.get("markdown")
            embed = kwargs.get("embed")

            if chat_id.startswith("group_"):
                group_openid = chat_id.replace("group_", "")
                return await self._send_group_message(
                    group_openid=group_openid,
                    content=content,
                    msg_type=msg_type,
                    msg_id=msg_id,
                    msg_seq=msg_seq,
                    images=images,
                    markdown=markdown,
                    embed=embed
                )
            elif chat_id.startswith("guild_"):
                channel_id = chat_id.replace("guild_", "")
                return await self._send_guild_message(
                    channel_id=channel_id,
                    content=content,
                    msg_id=msg_id,
                    images=images
                )
            else:
                return await self._send_c2c_message(
                    openid=chat_id,
                    content=content,
                    msg_type=msg_type,
                    msg_id=msg_id,
                    msg_seq=msg_seq,
                    images=images,
                    markdown=markdown,
                    embed=embed
                )

        except Exception as e:
            logger.error(f"[{self.name}] 发送消息失败: {e}")
            return {"success": False, "error": str(e)}

    async def _send_group_message(
        self,
        group_openid: str,
        content: str = "",
        msg_type: int = 0,
        msg_id: str = "",
        msg_seq: int = 1,
        images: List[str] = None,
        markdown: dict = None,
        embed: dict = None
    ) -> Dict[str, Any]:
        api = self._client.api
        images = images or []

        try:
            if images:
                for image_url in images:
                    media = await api.post_group_file(
                        group_openid=group_openid,
                        file_type=1,
                        url=image_url
                    )
                    result = await api.post_group_message(
                        group_openid=group_openid,
                        msg_type=7,
                        msg_id=msg_id,
                        msg_seq=msg_seq,
                        media=media
                    )
                    msg_seq += 1
                return {"success": True, "data": result}

            if markdown:
                result = await api.post_group_message(
                    group_openid=group_openid,
                    msg_type=2,
                    msg_id=msg_id,
                    msg_seq=msg_seq,
                    markdown=markdown
                )
                return {"success": True, "data": result}

            if embed:
                result = await api.post_group_message(
                    group_openid=group_openid,
                    msg_type=4,
                    msg_id=msg_id,
                    msg_seq=msg_seq,
                    embed=embed
                )
                return {"success": True, "data": result}

            result = await api.post_group_message(
                group_openid=group_openid,
                msg_type=0,
                msg_id=msg_id,
                msg_seq=msg_seq,
                content=content
            )
            return {"success": True, "data": result}

        except Exception as e:
            logger.error(f"[{self.name}] 群消息发送失败: {e}")
            return {"success": False, "error": str(e)}

    async def _send_c2c_message(
        self,
        openid: str,
        content: str = "",
        msg_type: int = 0,
        msg_id: str = "",
        msg_seq: int = 1,
        images: List[str] = None,
        markdown: dict = None,
        embed: dict = None
    ) -> Dict[str, Any]:
        api = self._client.api
        images = images or []

        try:
            if images:
                for image_url in images:
                    media = await api.post_c2c_file(
                        openid=openid,
                        file_type=1,
                        url=image_url
                    )
                    result = await api.post_c2c_message(
                        openid=openid,
                        msg_type=7,
                        msg_id=msg_id,
                        msg_seq=msg_seq,
                        media=media
                    )
                    msg_seq += 1
                return {"success": True, "data": result}

            if markdown:
                result = await api.post_c2c_message(
                    openid=openid,
                    msg_type=2,
                    msg_id=msg_id,
                    msg_seq=msg_seq,
                    markdown=markdown
                )
                return {"success": True, "data": result}

            if embed:
                result = await api.post_c2c_message(
                    openid=openid,
                    msg_type=4,
                    msg_id=msg_id,
                    msg_seq=msg_seq,
                    embed=embed
                )
                return {"success": True, "data": result}

            result = await api.post_c2c_message(
                openid=openid,
                msg_type=0,
                msg_id=msg_id,
                msg_seq=msg_seq,
                content=content
            )
            return {"success": True, "data": result}

        except Exception as e:
            logger.error(f"[{self.name}] 私聊消息发送失败: {e}")
            return {"success": False, "error": str(e)}

    async def _send_guild_message(
        self,
        channel_id: str,
        content: str = "",
        msg_id: str = "",
        images: List[str] = None
    ) -> Dict[str, Any]:
        api = self._client.api
        images = images or []

        try:
            result = await api.post_message(
                channel_id=channel_id,
                content=content,
                msg_id=msg_id,
                file_image=images[0] if images else None
            )
            return {"success": True, "data": result}

        except Exception as e:
            logger.error(f"[{self.name}] 频道消息发送失败: {e}")
            return {"success": False, "error": str(e)}

    async def send_text(self, target: Dict[str, str], content: str, **kwargs) -> Dict[str, Any]:
        return await self.send_message(target, content, msg_type=0, **kwargs)

    async def send_image(
        self,
        target: Dict[str, str],
        image_url: str = None,
        image_path: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        images = []
        if image_url:
            images.append(image_url)
        elif image_path:
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
            kwargs["image_base64"] = image_data

        return await self.send_message(target, "", msg_type=7, images=images, **kwargs)

    async def send_video(
        self,
        target: Dict[str, str],
        video_url: str = None,
        video_path: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送视频消息

        Args:
            target: 目标信息
            video_url: 视频 URL
            video_path: 本地视频路径

        Returns:
            发送结果
        """
        if not self._client or not self._client.api:
            return {"success": False, "error": "botpy 客户端未初始化"}

        api = self._client.api
        chat_id = target.get("chat_id", "")
        msg_id = kwargs.get("msg_id", "")
        msg_seq = kwargs.get("msg_seq", 1)

        try:
            if video_path:
                with open(video_path, "rb") as f:
                    video_data = base64.b64encode(f.read()).decode("utf-8")

                if chat_id.startswith("group_"):
                    group_openid = chat_id.replace("group_", "")
                    media = await api.post_group_base64file(
                        group_openid=group_openid,
                        file_type=2,
                        file_data=video_data
                    )
                    result = await api.post_group_message(
                        group_openid=group_openid,
                        msg_type=7,
                        msg_id=msg_id,
                        msg_seq=msg_seq,
                        media=media
                    )
                else:
                    media = await api.post_c2c_base64file(
                        openid=chat_id,
                        file_type=2,
                        file_data=video_data
                    )
                    result = await api.post_c2c_message(
                        openid=chat_id,
                        msg_type=7,
                        msg_id=msg_id,
                        msg_seq=msg_seq,
                        media=media
                    )
            elif video_url:
                if chat_id.startswith("group_"):
                    group_openid = chat_id.replace("group_", "")
                    media = await api.post_group_file(
                        group_openid=group_openid,
                        file_type=2,
                        url=video_url
                    )
                    result = await api.post_group_message(
                        group_openid=group_openid,
                        msg_type=7,
                        msg_id=msg_id,
                        msg_seq=msg_seq,
                        media=media
                    )
                else:
                    media = await api.post_c2c_file(
                        openid=chat_id,
                        file_type=2,
                        url=video_url
                    )
                    result = await api.post_c2c_message(
                        openid=chat_id,
                        msg_type=7,
                        msg_id=msg_id,
                        msg_seq=msg_seq,
                        media=media
                    )
            else:
                return {"success": False, "error": "需要提供 video_url 或 video_path"}

            return {"success": True, "data": result}

        except Exception as e:
            logger.error(f"[{self.name}] 视频发送失败: {e}")
            return {"success": False, "error": str(e)}

    async def send_voice(
        self,
        target: Dict[str, str],
        voice_url: str = None,
        voice_path: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送语音消息

        Args:
            target: 目标信息
            voice_url: 语音 URL（仅支持 silk 格式）
            voice_path: 本地语音路径

        Returns:
            发送结果
        """
        if not self._client or not self._client.api:
            return {"success": False, "error": "botpy 客户端未初始化"}

        api = self._client.api
        chat_id = target.get("chat_id", "")
        msg_id = kwargs.get("msg_id", "")
        msg_seq = kwargs.get("msg_seq", 1)

        try:
            if voice_path:
                with open(voice_path, "rb") as f:
                    voice_data = base64.b64encode(f.read()).decode("utf-8")

                if chat_id.startswith("group_"):
                    group_openid = chat_id.replace("group_", "")
                    media = await api.post_group_base64file(
                        group_openid=group_openid,
                        file_type=3,
                        file_data=voice_data
                    )
                    result = await api.post_group_message(
                        group_openid=group_openid,
                        msg_type=7,
                        msg_id=msg_id,
                        msg_seq=msg_seq,
                        media=media
                    )
                else:
                    media = await api.post_c2c_base64file(
                        openid=chat_id,
                        file_type=3,
                        file_data=voice_data
                    )
                    result = await api.post_c2c_message(
                        openid=chat_id,
                        msg_type=7,
                        msg_id=msg_id,
                        msg_seq=msg_seq,
                        media=media
                    )
            elif voice_url:
                if chat_id.startswith("group_"):
                    group_openid = chat_id.replace("group_", "")
                    media = await api.post_group_file(
                        group_openid=group_openid,
                        file_type=3,
                        url=voice_url
                    )
                    result = await api.post_group_message(
                        group_openid=group_openid,
                        msg_type=7,
                        msg_id=msg_id,
                        msg_seq=msg_seq,
                        media=media
                    )
                else:
                    media = await api.post_c2c_file(
                        openid=chat_id,
                        file_type=3,
                        url=voice_url
                    )
                    result = await api.post_c2c_message(
                        openid=chat_id,
                        msg_type=7,
                        msg_id=msg_id,
                        msg_seq=msg_seq,
                        media=media
                    )
            else:
                return {"success": False, "error": "需要提供 voice_url 或 voice_path"}

            return {"success": True, "data": result}

        except Exception as e:
            logger.error(f"[{self.name}] 语音发送失败: {e}")
            return {"success": False, "error": str(e)}

    async def send_markdown(self, target: Dict[str, str], markdown: dict, **kwargs) -> Dict[str, Any]:
        return await self.send_message(target, "", msg_type=2, markdown=markdown, **kwargs)

    async def send_embed(self, target: Dict[str, str], embed: dict, **kwargs) -> Dict[str, Any]:
        return await self.send_message(target, "", msg_type=4, embed=embed, **kwargs)

    async def send_file(
        self,
        target: Dict[str, str],
        file_url: str = None,
        file_path: str = None,
        file_name: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送文件消息（仅支持 C2C 单聊）

        Args:
            target: 目标信息，chat_id 为用户 openid
            file_url: 文件的公网可下载链接
            file_path: 本地文件路径
            file_name: 自定义显示的文件名（可选）

        Returns:
            发送结果

        注意:
            - 仅支持 QQ 单聊（C2C）场景
            - 群聊不支持发送文件（file_type=4 未开放）
            - 文件需先上传至公网可访问的服务器/OSS
        """
        if not self._client or not self._client.api:
            return {"success": False, "error": "botpy 客户端未初始化"}

        api = self._client.api
        chat_id = target.get("chat_id", "")
        msg_id = kwargs.get("msg_id", "")
        msg_seq = kwargs.get("msg_seq", 1)

        if chat_id.startswith("group_"):
            return {
                "success": False,
                "error": "群聊不支持发送文件，仅支持 C2C 单聊场景"
            }

        try:
            if file_path:
                with open(file_path, "rb") as f:
                    file_data = base64.b64encode(f.read()).decode("utf-8")

                media = await api.post_c2c_base64file(
                    openid=chat_id,
                    file_type=4,
                    file_data=file_data
                )
            elif file_url:
                media = await api.post_c2c_file(
                    openid=chat_id,
                    file_type=4,
                    url=file_url
                )
            else:
                return {"success": False, "error": "需要提供 file_url 或 file_path"}

            media_dict = {}
            if hasattr(media, '__dict__'):
                media_dict = {k: v for k, v in media.__dict__.items() if not k.startswith('_')}
            elif isinstance(media, dict):
                media_dict = media

            if file_name:
                media_dict['file_name'] = file_name

            result = await api.post_c2c_message(
                openid=chat_id,
                msg_type=7,
                msg_id=msg_id,
                msg_seq=msg_seq,
                media=media_dict
            )

            return {"success": True, "data": result}

        except Exception as e:
            logger.error(f"[{self.name}] 文件发送失败: {e}")
            return {"success": False, "error": str(e)}

    async def _convert_to_unified(self, raw: Any, attachment_results: Dict[str, List] = None) -> UnifiedMessage:
        message_type = self._get_message_type(raw)

        if message_type == "guild":
            chat_id = f"guild_{getattr(raw, 'channel_id', '')}"
            user_id = str(getattr(raw.author, 'id', '')) if hasattr(raw, 'author') else ""
        elif message_type == "group":
            chat_id = f"group_{getattr(raw, 'group_openid', '')}"
            user_id = str(getattr(raw.author, 'member_openid', '')) if hasattr(raw, 'author') else ""
        elif message_type == "direct":
            chat_id = f"guild_{getattr(raw, 'channel_id', '')}"
            user_id = str(getattr(raw.author, 'id', '')) if hasattr(raw, 'author') else ""
        elif message_type == "c2c":
            chat_id = str(getattr(raw.author, 'user_openid', '')) if hasattr(raw, 'author') else ""
            user_id = chat_id
        else:
            chat_id = ""
            user_id = ""

        content = getattr(raw, 'content', '') or ""
        
        # 构建标准的 attachments 结构
        attachments = []
        images = []
        
        if attachment_results:
            # 处理图片
            for img_result in attachment_results.get("images", []):
                base64_data = img_result.get("base64_data", "")
                if base64_data:
                    content_type = img_result.get("content_type", "image/jpeg")
                    filename = img_result.get("filename", "image.jpg")
                    size = img_result.get("size", 0)
                    
                    # 构建 base64 URL
                    image_url = f"data:{content_type};base64,{base64_data}"
                    images.append(image_url)
                    
                    # 添加到 attachments
                    attachments.append({
                        "type": "image",
                        "filename": filename,
                        "content_type": content_type,
                        "size": size,
                        "base64": image_url
                    })
            
            # 处理其他文件类型
            for file_result in attachment_results.get("files", []):
                attachments.append({
                    "type": "document",
                    "filename": file_result.get("filename", "unknown"),
                    "content_type": file_result.get("content_type", "application/octet-stream"),
                    "size": file_result.get("size", 0),
                    "url": file_result.get("url"),
                    "base64": file_result.get("base64_data")
                })
            
            # 处理视频
            for video_result in attachment_results.get("videos", []):
                attachments.append({
                    "type": "video",
                    "filename": video_result.get("filename", "video.mp4"),
                    "content_type": video_result.get("content_type", "video/mp4"),
                    "size": video_result.get("size", 0),
                    "url": video_result.get("url"),
                    "base64": video_result.get("base64_data")
                })
            
            # 处理音频
            for audio_result in attachment_results.get("voices", []):
                attachments.append({
                    "type": "audio",
                    "filename": audio_result.get("filename", "audio.mp3"),
                    "content_type": audio_result.get("content_type", "audio/mpeg"),
                    "size": audio_result.get("size", 0),
                    "url": audio_result.get("url"),
                    "base64": audio_result.get("base64_data")
                })
        
        # 如果没有下载的附件，尝试从 URL 提取图片
        if not images:
            images = await self._extract_images(raw)

        raw_dict = self._message_to_dict(raw)

        return UnifiedMessage(
            id=str(getattr(raw, 'id', '')),
            listener=self.name,
            platform=self.PLATFORM_NAME,
            type=message_type,
            content=content,
            images=images,
            attachments=attachments,
            user_id=user_id,
            chat_id=chat_id,
            thread_id=None,
            timestamp=time.time(),
            raw=raw_dict
        )
    
    async def _publish_incoming(self, raw_data: Any, attachment_results: Dict[str, List] = None) -> None:
        """
        将原始消息转换为统一格式并发布到总线
        
        Args:
            raw_data: 原始消息对象
            attachment_results: 已下载的附件结果（包含 base64 图片）
        """
        try:
            unified = await self._convert_to_unified(raw_data, attachment_results=attachment_results)
            unified.listener = self.name
            
            await self.bus.publish(
                "incoming",
                unified.to_dict(),
                source=self.name
            )
            
            logger.debug(
                f"[{self.name}] 消息已发布: chat_id={unified.chat_id}, "
                f"user_id={unified.user_id}, type={unified.type}, images={len(unified.images)}"
            )
        except Exception as e:
            logger.error(f"[{self.name}] 消息转换失败: {e}")

    def _get_message_type(self, message) -> str:
        if isinstance(message, Message):
            return "guild"
        elif isinstance(message, GroupMessage):
            return "group"
        elif isinstance(message, DirectMessage):
            return "direct"
        else:
            return "c2c"

    async def _extract_images(self, message) -> List[str]:
        attachments = getattr(message, 'attachments', None)
        if not attachments:
            return []

        images = []
        for att in attachments:
            content_type = getattr(att, 'content_type', '')
            if 'image' in content_type:
                url = getattr(att, 'url', '')
                if url:
                    images.append(url)

        return images

    def _message_to_dict(self, message) -> Dict[str, Any]:
        result = {}
        for attr in ['id', 'content', 'channel_id', 'group_openid', 'timestamp']:
            if hasattr(message, attr):
                result[attr] = getattr(message, attr)

        if hasattr(message, 'author'):
            author = message.author
            result['author'] = {}
            for attr in ['id', 'user_openid', 'member_openid', 'username']:
                if hasattr(author, attr):
                    result['author'][attr] = getattr(author, attr)

        if hasattr(message, 'attachments'):
            result['attachments'] = []
            for att in message.attachments:
                att_dict = {}
                for attr in ['url', 'filename', 'content_type', 'size', 'width', 'height']:
                    if hasattr(att, attr):
                        att_dict[attr] = getattr(att, attr)
                result['attachments'].append(att_dict)

        return result

    async def download_and_process_attachments(self, message) -> Dict[str, List[Dict[str, Any]]]:
        """
        下载并处理消息中的所有附件（图片、文件、语音、视频）

        Args:
            message: 消息对象

        Returns:
            处理结果字典，包含:
            - images: 图片列表
            - files: 文件列表
            - voices: 语音列表
            - videos: 视频列表
            每个元素包含:
            - url: 原始URL
            - local_path: 本地保存路径
            - base64_data: base64编码数据
            - content_type: 类型
            - filename: 文件名
            - size: 文件大小
        """
        attachments = getattr(message, 'attachments', None)
        if not attachments:
            return {"images": [], "files": [], "voices": [], "videos": []}

        results = {
            "images": [],
            "files": [],
            "voices": [],
            "videos": []
        }

        save_dirs = self._get_all_save_dirs()
        for dir_path in save_dirs.values():
            os.makedirs(dir_path, exist_ok=True)

        for att in attachments:
            content_type = getattr(att, 'content_type', '')
            url = getattr(att, 'url', '')
            filename = getattr(att, 'filename', '')
            size = getattr(att, 'size', 0)

            if not url:
                continue

            att_type = self._get_attachment_type(content_type)
            save_dir = save_dirs.get(att_type, save_dirs["files"])

            try:
                data = await self._download_file(url)
                if not data:
                    continue

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                ext = self._get_extension_by_type(content_type, att_type)
                local_filename = f"{timestamp}_{filename}"
                if ext and not local_filename.endswith(ext):
                    local_filename += ext
                local_path = os.path.join(save_dir, local_filename)

                with open(local_path, 'wb') as f:
                    f.write(data)
                logger.info(f"[{self.name}] ✅ {att_type}已保存到: {local_path}")

                base64_data = base64.b64encode(data).decode('utf-8')
                logger.info(f"[{self.name}] ✅ {att_type}已转换为base64, 长度: {len(base64_data)}")

                result_item = {
                    "url": url,
                    "local_path": local_path,
                    "base64_data": base64_data,
                    "content_type": content_type,
                    "filename": filename,
                    "size": size,
                }

                results[att_type].append(result_item)

            except Exception as e:
                logger.error(f"[{self.name}] 处理{att_type}失败: {e}")

        return results

    def _get_all_save_dirs(self) -> Dict[str, str]:
        """
        获取所有附件类型的保存目录

        Returns:
            目录映射字典
        """
        base_dir = self._image_save_dir
        parent_dir = os.path.dirname(base_dir)
        return {
            "images": base_dir,
            "files": os.path.join(parent_dir, "downloaded_files"),
            "voices": os.path.join(parent_dir, "downloaded_voices"),
            "videos": os.path.join(parent_dir, "downloaded_videos"),
        }

    def _get_attachment_type(self, content_type: str) -> str:
        """
        根据content_type判断附件类型

        Args:
            content_type: MIME类型

        Returns:
            附件类型: images/files/voices/videos
        """
        content_type_lower = content_type.lower()
        if 'image' in content_type_lower:
            return "images"
        elif 'video' in content_type_lower:
            return "videos"
        elif 'voice' in content_type_lower or 'audio' in content_type_lower:
            return "voices"
        else:
            return "files"

    async def _download_file(self, url: str) -> Optional[bytes]:
        """
        下载文件数据

        Args:
            url: 文件URL

        Returns:
            文件二进制数据
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status == 200:
                        data = await response.read()
                        logger.info(f"[{self.name}] 📥 文件下载成功, 大小: {len(data)} bytes")
                        return data
                    else:
                        logger.error(f"[{self.name}] ❌ 文件下载失败, HTTP状态: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"[{self.name}] ❌ 文件下载异常: {e}")
            return None

    @staticmethod
    def _get_extension_by_type(content_type: str, att_type: str) -> str:
        """
        根据content_type和附件类型获取文件扩展名

        Args:
            content_type: MIME类型
            att_type: 附件类型

        Returns:
            文件扩展名
        """
        image_ext_map = {
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp',
            'image/bmp': '.bmp',
        }
        video_ext_map = {
            'video/mp4': '.mp4',
            'video/webm': '.webm',
            'video/quicktime': '.mov',
            'video/x-msvideo': '.avi',
        }
        audio_ext_map = {
            'audio/mpeg': '.mp3',
            'audio/wav': '.wav',
            'audio/ogg': '.ogg',
            'audio/aac': '.aac',
            'audio/amr': '.amr',
            'audio/silk': '.silk',
        }

        content_type_lower = content_type.lower()

        if att_type == "images":
            return image_ext_map.get(content_type_lower, '.jpg')
        elif att_type == "videos":
            return video_ext_map.get(content_type_lower, '.mp4')
        elif att_type == "voices":
            return audio_ext_map.get(content_type_lower, '.mp3')
        else:
            return ''

    async def download_and_process_images(self, message) -> List[Dict[str, Any]]:
        """
        下载并处理消息中的图片附件（兼容旧接口）

        Args:
            message: 消息对象

        Returns:
            处理结果列表
        """
        results = await self.download_and_process_attachments(message)
        return results.get("images", [])

    def _on_at_message_create(self, message: Message):
        logger.info(f"[{self.name}] 📢 [频道] 收到@消息: {message.content}")
        self._create_task(self._handle_guild_message(message), name=f"{self.name}_guild_msg")

    def _on_group_at_message_create(self, message: GroupMessage):
        attachments_info = self._parse_attachments(message)
        logger.info(f"[{self.name}] 💬 [群聊] 收到@消息: {message.content}{attachments_info}")
        self._create_task(self._handle_group_message(message), name=f"{self.name}_group_msg")

    def _on_direct_message_create(self, message: DirectMessage):
        attachments_info = self._parse_attachments(message)
        logger.info(f"[{self.name}] ✉️ [频道私信] 收到消息: {message.content}{attachments_info}")
        self._create_task(self._handle_direct_message(message), name=f"{self.name}_direct_msg")

    def _on_c2c_message_create(self, message):
        attachments_info = self._parse_attachments(message)
        logger.info(f"[{self.name}] 💌 [私聊] 收到消息: {message.content}{attachments_info}")
        self._create_task(self._handle_c2c_message(message), name=f"{self.name}_c2c_msg")

    async def _handle_guild_message(self, message: Message):
        await self._publish_incoming(message)

    async def _handle_group_message(self, message: GroupMessage):
        all_results = await self.download_and_process_attachments(message)
        self._log_attachment_summary(all_results)
        await self._publish_incoming(message, attachment_results=all_results)

    async def _handle_direct_message(self, message: DirectMessage):
        await self._publish_incoming(message)

    async def _handle_c2c_message(self, message):
        all_results = await self.download_and_process_attachments(message)
        self._log_attachment_summary(all_results)
        await self._publish_incoming(message, attachment_results=all_results)

    def _log_attachment_summary(self, results: Dict[str, List]):
        """
        记录附件处理摘要

        Args:
            results: 附件处理结果字典
        """
        summary_parts = []
        if results["images"]:
            summary_parts.append(f"📸 {len(results['images'])} 张图片")
        if results["files"]:
            summary_parts.append(f"📄 {len(results['files'])} 个文件")
        if results["voices"]:
            summary_parts.append(f"🎤 {len(results['voices'])} 条语音")
        if results["videos"]:
            summary_parts.append(f"🎬 {len(results['videos'])} 个视频")

        if summary_parts:
            logger.info(f"[{self.name}] 共处理附件: {', '.join(summary_parts)}")

    def _parse_attachments(self, message) -> str:
        attachments = getattr(message, 'attachments', None)
        if not attachments:
            return ""

        info_parts = []
        for att in attachments:
            content_type = getattr(att, 'content_type', '')
            filename = getattr(att, 'filename', '')
            size = getattr(att, 'size', 0)
            width = getattr(att, 'width', 0)
            height = getattr(att, 'height', 0)

            if 'image' in content_type:
                info_parts.append(f"\n  📷 图片: {filename} ({width}x{height}, {size} bytes)")
            elif 'video' in content_type:
                info_parts.append(f"\n  🎬 视频: {filename} ({size} bytes)")
            elif 'voice' in content_type or 'audio' in content_type:
                info_parts.append(f"\n  🎤 语音: {filename}")
            elif content_type == 'file':
                info_parts.append(f"\n  📄 文件: {filename} ({size} bytes)")

        return "".join(info_parts) if info_parts else ""


class _BotpyClientWrapper(botpy.Client):
    """
    botpy.Client 包装类

    功能说明:
        - 继承 botpy.Client，将消息回调转发到 QQListener
        - 支持频道、群聊、私聊消息回调

    核心方法:
        - on_ready: 机器人就绪回调
        - on_at_message_create: 频道@消息回调
        - on_group_at_message_create: 群聊@消息回调
        - on_direct_message_create: 频道私信消息回调
        - on_c2c_message_create: 用户单聊消息回调
    """

    def __init__(self, intents: botpy.Intents, listener: QQListener):
        super().__init__(intents=intents)
        self._listener = listener

    async def on_ready(self):
        logger.info(f"[{self._listener.name}] 🤖 机器人「{self.robot.name}」已上线！")

    async def on_at_message_create(self, message: Message):
        self._listener._on_at_message_create(message)

    async def on_group_at_message_create(self, message: GroupMessage):
        self._listener._on_group_at_message_create(message)

    async def on_direct_message_create(self, message: DirectMessage):
        self._listener._on_direct_message_create(message)

    async def on_c2c_message_create(self, message):
        self._listener._on_c2c_message_create(message)
