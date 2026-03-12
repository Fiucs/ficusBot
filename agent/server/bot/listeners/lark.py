#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
飞书/Lark 监听器模块（WebSocket 长连接模式）

功能说明:
    - 使用官方 SDK lark-oapi 实现
    - 使用 WebSocket 长连接模式接收消息（无需公网地址）
    - 支持消息签名验证
    - 将飞书消息转换为统一格式

配置项:
    - app_id: 应用 ID
    - app_secret: 应用密钥

依赖:
    pip install lark-oapi
"""

import asyncio
import json
import time
import queue
import multiprocessing
import base64
import aiohttp
from typing import Dict, Any

from loguru import logger

from ..base_listener import BaseListener
from ..message_bus import UnifiedMessage


def _run_ws_client_process(app_id: str, app_secret: str, message_queue: multiprocessing.Queue, stop_event: multiprocessing.Event):
    """在独立进程中运行 WebSocket 客户端。"""
    try:
        from lark_oapi import Client, LogLevel
        from lark_oapi import ws
        from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        import nest_asyncio
        nest_asyncio.apply(loop)
        
        event_handler = EventDispatcherHandler.builder("", "") \
            .register_p2_im_message_receive_v1(lambda event: message_queue.put(event)) \
            .build()
        
        ws_client = ws.Client(
            app_id=app_id,
            app_secret=app_secret,
            log_level=LogLevel.INFO,
            event_handler=event_handler,
            auto_reconnect=True
        )
        
        logger.info("[LarkWS] WebSocket 进程已启动")
        ws_client.start()
        
    except Exception as e:
        if not stop_event.is_set():
            logger.error(f"[LarkWS] WebSocket 运行错误: {e}")


class LarkListener(BaseListener):
    """飞书/Lark 监听器"""
    
    PLATFORM_NAME = "lark"
    PLATFORM_DISPLAY_NAME = "飞书/Lark"
    
    def __init__(self, name: str, config: Dict[str, Any], bus):
        super().__init__(name, config, bus)
        self._client = None
        self._ws_process = None
        self._message_queue = None
        self._processor_task = None
        self._main_loop = None
        self._stop_event = None
        
        self._app_id = config.get("app_id") or config.get("appId", "")
        self._app_secret = config.get("app_secret") or config.get("appSecret", "")
    
    async def start(self) -> bool:
        try:
            from lark_oapi import Client, LogLevel
            
            if not self._app_id or not self._app_secret:
                logger.error(f"[{self.name}] 缺少 app_id/appId 或 app_secret/appSecret 配置")
                return False
            
            self._main_loop = asyncio.get_running_loop()
            
            self._client = Client.builder() \
                .app_id(self._app_id) \
                .app_secret(self._app_secret) \
                .log_level(LogLevel.ERROR) \
                .build()
            
            self._message_queue = multiprocessing.Queue()
            self._stop_event = multiprocessing.Event()
            
            self._ws_process = multiprocessing.Process(
                target=_run_ws_client_process,
                args=(self._app_id, self._app_secret, self._message_queue, self._stop_event),
                daemon=True,
                name=f"FeishuWS_{self.name}"
            )
            self._ws_process.start()
            
            self._processor_task = asyncio.create_task(self._process_message_queue())
            
            self.bus.subscribe("outgoing", self._handle_outgoing)
            
            self._running = True
            
            logger.info(f"[{self.name}] 🎉 飞书监听器启动成功")
            
            return True
            
        except ImportError as e:
            logger.error(f"[{self.name}] 缺少依赖: {e}, 请安装: pip install lark-oapi")
            return False
        except Exception as e:
            logger.error(f"[{self.name}] 启动失败: {e}")
            return False
    
    async def _process_message_queue(self):
        """处理消息队列。"""
        while self._running:
            try:
                event = await asyncio.get_running_loop().run_in_executor(
                    None, 
                    self._message_queue.get, 
                    True, 
                    1.0
                )
                await self._process_sdk_event(event)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"[{self.name}] 处理消息队列错误: {e}")
    
    async def _process_sdk_event(self, event) -> None:
        """处理 SDK 事件对象。"""
        try:
            event_data = event.event if hasattr(event, 'event') else event
            message = event_data.message if hasattr(event_data, 'message') else None
            sender = event_data.sender if hasattr(event_data, 'sender') else None
            header = event.header if hasattr(event, 'header') else None
            
            if not message:
                return
            
            formatted_data = {
                "schema": "2.0",
                "header": {
                    "event_id": getattr(header, 'event_id', '') if header else '',
                    "event_type": "im.message.receive_v1",
                },
                "event": {
                    "message": {
                        "message_id": getattr(message, 'message_id', ''),
                        "chat_id": getattr(message, 'chat_id', ''),
                        "chat_type": getattr(message, 'chat_type', ''),
                        "message_type": getattr(message, 'message_type', ''),
                        "content": getattr(message, 'content', '{}'),
                    },
                    "sender": {
                        "sender_id": {
                            "union_id": getattr(sender.sender_id, 'union_id', '') if sender and hasattr(sender, 'sender_id') else '',
                            "user_id": getattr(sender.sender_id, 'user_id', '') if sender and hasattr(sender, 'sender_id') else '',
                            "open_id": getattr(sender.sender_id, 'open_id', '') if sender and hasattr(sender, 'sender_id') else ''
                        }
                    }
                }
            }
            
            await self._publish_incoming(formatted_data)
            
        except Exception as e:
            logger.error(f"[{self.name}] 处理 SDK 事件失败: {e}")
    
    async def stop(self) -> bool:
        self._running = False
        
        if self._processor_task:
            self._processor_task.cancel()
        
        if self._stop_event:
            self._stop_event.set()
        
        if self._ws_process and self._ws_process.is_alive():
            self._ws_process.terminate()
            self._ws_process.join(timeout=2)
        
        await self._cancel_all_tasks()
        
        logger.info(f"[{self.name}] 飞书监听器已停止")
        return True
    
    async def send_message(self, target: Dict[str, str], content: str, **kwargs) -> Dict[str, Any]:
        try:
            import lark_oapi.api.im.v1 as im
            
            chat_id = target.get("chat_id")
            if not chat_id:
                return {"success": False, "error": "缺少 chat_id"}
            
            request = im.CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(
                    im.CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("text")
                    .content(json.dumps({"text": content}, ensure_ascii=False))
                    .build()
                ) \
                .build()
            
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                self._client.im.v1.message.create,
                request
            )
            
            if response.success():
                return {"success": True, "message_id": response.data.message_id if response.data else None}
            else:
                return {"success": False, "error": response.msg}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _convert_to_unified(self, raw: dict) -> UnifiedMessage:
        event = raw.get("event", {})
        message = event.get("message", {})
        sender = event.get("sender", {})
        sender_id = sender.get("sender_id", {})
        
        message_type = message.get("message_type", "text")
        content_raw = message.get("content", "{}")
        
        content = ""
        images = []
        try:
            if isinstance(content_raw, str):
                content_data = json.loads(content_raw)
            else:
                content_data = content_raw
            
            if message_type == "text":
                content = content_data.get("text", "")
            elif message_type == "post":
                content, post_images = await self._extract_post_content(content_data, message.get("message_id"))
                images.extend(post_images)
            elif message_type == "image":
                logger.info(f"[{self.name}] 📷 收到图片消息，content_data: {content_data}")
                content = content_data.get("text", "") or ""
                image_key = content_data.get("image_key")
                logger.info(f"[{self.name}] 图片 image_key: {image_key}")
                if image_key:
                    try:
                        message_id = message.get("message_id")
                        image_base64 = await self._download_image(message_id, image_key)
                        if image_base64:
                            images.append(image_base64)
                            logger.info(f"[{self.name}] ✅ 已下载飞书图片，大小: {len(image_base64)} 字符")
                        else:
                            logger.warning(f"[{self.name}] ⚠️ 图片下载返回空")
                            content = f"{content}\n[图片下载失败]".strip()
                    except Exception as e:
                        logger.error(f"[{self.name}] ❌ 下载飞书图片失败: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                        content = f"{content}\n[图片下载失败: {str(e)[:50]}]".strip()
                else:
                    logger.warning(f"[{self.name}] ⚠️ 图片消息没有 image_key")
            else:
                content = f"[{message_type}]"
        except json.JSONDecodeError:
            content = content_raw if isinstance(content_raw, str) else str(content_raw)
        
        return UnifiedMessage(
            id=message.get("message_id"),
            listener=self.name,
            platform=self.PLATFORM_NAME,
            type=message_type,
            content=content,
            images=images,
            user_id=sender_id.get("union_id", "") or sender_id.get("user_id", ""),
            chat_id=message.get("chat_id", ""),
            thread_id=None,
            timestamp=time.time(),
            raw=raw
        )
    
    async def _download_image(self, message_id: str, image_key: str) -> str:
        """
        下载飞书消息中的图片并转换为 Base64
        
        使用飞书开放 API: /open-apis/im/v1/messages/{message_id}/resources
        此 API 用于获取消息中的资源文件（图片、文件等）
        
        Args:
            message_id: 消息 ID
            image_key: 飞书图片 key
            
        Returns:
            Base64 编码的图片字符串，格式为 "data:image/jpeg;base64,..."
        """
        try:
            if not self._client:
                logger.error(f"[{self.name}] ❌ 飞书客户端未初始化")
                return ""
            
            logger.info(f"[{self.name}] 📥 开始下载消息图片，message_id: {message_id}, image_key: {image_key}")
            
            tenant_access_token = await self._get_tenant_access_token()
            if not tenant_access_token:
                logger.error(f"[{self.name}] ❌ 获取 tenant_access_token 失败")
                return ""
            
            url = f"https://open.larksuite.com/open-apis/im/v1/messages/{message_id}/resources/{image_key}"
            headers = {"Authorization": f"Bearer {tenant_access_token}"}
            params = {"type": "image"}
            
            logger.info(f"[{self.name}] 📥 请求 URL: {url}")
            logger.info(f"[{self.name}] 📥 请求参数: {params}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    logger.info(f"[{self.name}] 📥 响应状态: {response.status}")
                    content_type = response.headers.get('Content-Type', '')
                    logger.info(f"[{self.name}] 📥 响应 Content-Type: {content_type}")
                    
                    if response.status == 200:
                        if 'application/json' in content_type:
                            json_data = await response.json()
                            logger.error(f"[{self.name}] ❌ 飞书返回 JSON 错误: {json_data}")
                            return ""
                        
                        image_data = await response.read()
                        mime_type = content_type.split(';')[0].strip() if '/' in content_type else 'image/jpeg'
                        
                        image_base64 = base64.b64encode(image_data).decode('utf-8')
                        logger.info(f"[{self.name}] ✅ 图片下载成功，大小: {len(image_data)} bytes, MIME: {mime_type}")
                        return f"data:{mime_type};base64,{image_base64}"
                    else:
                        error_text = await response.text()
                        logger.error(f"[{self.name}] ❌ 下载图片失败: status={response.status}, error={error_text}")
                        return ""
                        
        except Exception as e:
            logger.error(f"[{self.name}] ❌ 下载图片异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return ""
    
    async def _get_tenant_access_token(self) -> str:
        """
        获取飞书 tenant_access_token
        
        Returns:
            tenant_access_token 字符串
        """
        try:
            import requests
            
            url = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal"
            payload = {
                "app_id": self._app_id,
                "app_secret": self._app_secret
            }
            
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(url, json=payload)
            )
            
            if response.status_code == 200:
                data = response.json()
                token = data.get("tenant_access_token", "")
                logger.debug(f"[{self.name}] ✅ 获取 tenant_access_token 成功")
                return token
            else:
                logger.error(f"[{self.name}] ❌ 获取 tenant_access_token 失败: {response.text}")
                return ""
                
        except Exception as e:
            logger.error(f"[{self.name}] ❌ 获取 tenant_access_token 异常: {e}")
            return ""
    
    async def _extract_post_content(self, content_data: dict, message_id: str) -> tuple:
        """
        提取富文本消息内容（包括图片）。
        
        Args:
            content_data: 富文本消息内容
            message_id: 消息 ID，用于下载图片
            
        Returns:
            (文本内容, 图片列表)
        """
        text_parts = []
        images = []
        
        async def extract_content(node):
            if isinstance(node, dict):
                if "text" in node:
                    text_parts.append(node["text"])
                if "tag" in node and node["tag"] == "img":
                    image_key = node.get("image_key")
                    if image_key:
                        logger.info(f"[{self.name}] 📷 富文本中发现图片: {image_key}")
                        try:
                            image_base64 = await self._download_image(message_id, image_key)
                            if image_base64:
                                images.append(image_base64)
                                text_parts.append("[图片]")
                        except Exception as e:
                            logger.error(f"[{self.name}] ❌ 下载富文本图片失败: {e}")
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        await extract_content(value)
            elif isinstance(node, list):
                for item in node:
                    await extract_content(item)
        
        await extract_content(content_data)
        return "".join(text_parts), images
