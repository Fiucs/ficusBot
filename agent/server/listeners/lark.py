#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :lark.py
# @Time      :2026/02/22
# @Author    :Ficus

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

参考:
    - 飞书开放平台: https://open.feishu.cn/
    - lark-oapi SDK: https://github.com/larksuite/oapi-sdk-python
"""

import asyncio
import json
import time
import queue
import multiprocessing
from typing import Dict, Any

from loguru import logger

from ..base_listener import BaseListener
from ..message_bus import UnifiedMessage


def _run_ws_client_process(app_id: str, app_secret: str, message_queue: multiprocessing.Queue, stop_event: multiprocessing.Event):
    """
    在独立进程中运行 WebSocket 客户端。
    
    Args:
        app_id: 飞书应用 ID
        app_secret: 飞书应用密钥
        message_queue: 消息队列（用于进程间通信）
        stop_event: 停止事件（用于进程间通信）
    """
    try:
        from lark_oapi import Client, LogLevel
        from lark_oapi import ws
        from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        import nest_asyncio
        nest_asyncio.apply(loop)
        
        class MessageHandler:
            def __init__(self, queue):
                self.queue = queue
            
            def handle(self, event):
                try:
                    self.queue.put(event)
                except Exception as e:
                    logger.error(f"[LarkWS] 消息入队失败: {e}")
        
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
            import traceback
            logger.error(f"[LarkWS] 错误详情:\n{traceback.format_exc()}")


class LarkListener(BaseListener):
    """
    飞书/Lark 监听器
    
    使用 lark-oapi 官方 SDK 的 WebSocket 长连接模式实现。
    无需公网地址，自动处理重连和心跳。
    
    功能说明:
        - WebSocket 长连接模式
        - 自动重连机制
        - 支持多种消息类型（文本、图片、文件等）
        - 支持私聊和群聊
    
    核心方法:
        - start: 启动监听器
        - stop: 停止监听器
        - send_message: 发送消息
        - _convert_to_unified: 转换消息格式
    
    配置示例:
        {
            "app_id": "cli_xxxxx",
            "app_secret": "xxxxx"
        }
    """
    
    PLATFORM_NAME = "lark"
    PLATFORM_DISPLAY_NAME = "飞书/Lark"
    
    def __init__(self, name: str, config: Dict[str, Any], bus):
        """
        初始化飞书监听器。
        
        Args:
            name: 监听器名称
            config: 配置字典
            bus: 消息总线实例
        """
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
        """
        启动飞书监听器。
        
        Returns:
            bool: 启动是否成功
        """
        try:
            from lark_oapi import Client, LogLevel
            
            if not self._app_id or not self._app_secret:
                logger.error(f"[{self.name}] 缺少 app_id/appId 或 app_secret/appSecret 配置")
                return False
            
            self._main_loop = asyncio.get_running_loop()
            
            logger.info(f"[{self.name}] 正在初始化飞书客户端...")
            logger.info(f"[{self.name}] App ID: {self._app_id}")
            logger.info(f"[{self.name}] App Secret: {self._app_secret[:8]}...{self._app_secret[-4:]}")
            
            self._client = Client.builder() \
                .app_id(self._app_id) \
                .app_secret(self._app_secret) \
                .log_level(LogLevel.ERROR) \
                .build()
            
            logger.info(f"[{self.name}] 飞书客户端初始化成功")
            
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
            
            logger.info(f"[{self.name}] ═════════════════════════════════════════")
            logger.info(f"[{self.name}] 🎉 飞书监听器启动成功")
            logger.info(f"[{self.name}] 📱 App ID: {self._app_id}")
            logger.info(f"[{self.name}] 🔌 连接模式: WebSocket 长连接（独立进程）")
            logger.info(f"[{self.name}] ═════════════════════════════════════════")
            
            return True
            
        except ImportError as e:
            logger.error(f"[{self.name}] 缺少依赖: {e}, 请安装: pip install lark-oapi")
            return False
        except Exception as e:
            logger.error(f"[{self.name}] 启动失败: {e}")
            import traceback
            logger.error(f"[{self.name}] 错误堆栈:\n{traceback.format_exc()}")
            return False
    
    async def _process_message_queue(self):
        """处理消息队列（在主事件循环中运行）。"""
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
        """
        处理 SDK 事件对象。
        
        Args:
            event: 飞书 SDK 事件对象
        """
        try:
            event_data = event.event if hasattr(event, 'event') else event
            message = event_data.message if hasattr(event_data, 'message') else None
            sender = event_data.sender if hasattr(event_data, 'sender') else None
            header = event.header if hasattr(event, 'header') else None
            
            if not message:
                logger.warning(f"[{self.name}] 事件没有 message 属性")
                return
            
            formatted_data = {
                "schema": "2.0",
                "header": {
                    "event_id": getattr(header, 'event_id', '') if header else '',
                    "create_time": getattr(header, 'create_time', '') if header else '',
                    "event_type": "im.message.receive_v1",
                    "app_id": getattr(header, 'app_id', '') if header else ''
                },
                "event": {
                    "message": {
                        "message_id": getattr(message, 'message_id', ''),
                        "chat_id": getattr(message, 'chat_id', ''),
                        "chat_type": getattr(message, 'chat_type', ''),
                        "message_type": getattr(message, 'message_type', ''),
                        "content": getattr(message, 'content', '{}'),
                        "create_time": getattr(message, 'create_time', '')
                    },
                    "sender": {
                        "sender_id": {
                            "union_id": getattr(sender.sender_id, 'union_id', '') if sender and hasattr(sender, 'sender_id') else '',
                            "user_id": getattr(sender.sender_id, 'user_id', '') if sender and hasattr(sender, 'sender_id') else '',
                            "open_id": getattr(sender.sender_id, 'open_id', '') if sender and hasattr(sender, 'sender_id') else ''
                        },
                        "sender_type": getattr(sender, 'sender_type', '') if sender else ''
                    }
                }
            }
            
            logger.info(f"[{self.name}] ✅ 消息格式化成功")
            logger.info(f"[{self.name}] 📨 来自 {formatted_data['event']['sender']['sender_id']['open_id']}")
            
            await self._publish_incoming(formatted_data)
            
        except Exception as e:
            logger.error(f"[{self.name}] 处理 SDK 事件失败: {e}")
            import traceback
            logger.error(f"[{self.name}] 错误堆栈:\n{traceback.format_exc()}")
    
    async def stop(self) -> bool:
        """
        停止飞书监听器。
        
        Returns:
            bool: 停止是否成功
        """
        try:
            self._running = False
            
            logger.info(f"[{self.name}] 正在停止...")
            
            if self._processor_task:
                self._processor_task.cancel()
                try:
                    await self._processor_task
                except asyncio.CancelledError:
                    pass
            
            if self._stop_event:
                self._stop_event.set()
            
            if self._ws_process and self._ws_process.is_alive():
                self._ws_process.terminate()
                self._ws_process.join(timeout=2)
            
            await self._cancel_all_tasks()
            
            logger.info(f"[{self.name}] 飞书监听器已停止")
            return True
            
        except Exception as e:
            logger.error(f"[{self.name}] 停止失败: {e}")
            return False
    
    async def send_message(self, target: Dict[str, str], content: str, **kwargs) -> Dict[str, Any]:
        """
        发送消息到飞书。
        
        Args:
            target: 目标信息字典，包含 chat_id
            content: 消息内容
            **kwargs: 其他参数
        
        Returns:
            Dict: 发送结果
        """
        try:
            import lark_oapi.api.im.v1 as im
            
            chat_id = target.get("chat_id")
            if not chat_id:
                logger.error(f"[{self.name}] 缺少 chat_id")
                return {"success": False, "error": "缺少 chat_id"}
            
            msg_type = "text"
            
            request = im.CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(
                    im.CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type(msg_type)
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
                logger.info(f"[{self.name}] 消息发送成功")
                return {"success": True, "message_id": response.data.message_id if response.data else None}
            else:
                logger.error(f"[{self.name}] 消息发送失败: {response.msg}")
                return {"success": False, "error": response.msg}
            
        except Exception as e:
            logger.error(f"[{self.name}] 发送消息失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def _handle_outgoing(self, data: dict) -> None:
        """
        处理 outgoing 事件。
        
        Args:
            data: 发送消息数据字典
        """
        if data.get("listener") != self.name:
            return
        
        target = {
            "chat_id": data.get("chat_id"),
            "thread_id": data.get("thread_id")
        }
        await self.send_message(target, data.get("content", ""))
    
    async def _convert_to_unified(self, raw: dict) -> UnifiedMessage:
        """
        将飞书消息转换为统一格式。
        
        Args:
            raw: 飞书事件推送的 JSON 数据
        
        Returns:
            UnifiedMessage: 统一格式消息
        """
        event = raw.get("event", {})
        message = event.get("message", {})
        sender = event.get("sender", {})
        sender_id = sender.get("sender_id", {})
        
        message_type = message.get("message_type", "text")
        content_raw = message.get("content", "{}")
        
        content = ""
        try:
            if isinstance(content_raw, str):
                content_data = json.loads(content_raw)
            else:
                content_data = content_raw
            
            if message_type == "text":
                content = content_data.get("text", "")
            elif message_type == "post":
                content = self._extract_post_content(content_data)
            elif message_type == "image":
                content = "[图片]"
            elif message_type == "file":
                content = f"[文件] {content_data.get('file_name', '')}"
            elif message_type == "audio":
                content = "[语音]"
            else:
                content = f"[{message_type}]"
        except json.JSONDecodeError:
            content = content_raw if isinstance(content_raw, str) else str(content_raw)
        
        create_time = message.get("create_time", 0)
        try:
            if isinstance(create_time, str):
                create_time = int(create_time)
            timestamp = create_time / 1000 if create_time else time.time()
        except (ValueError, TypeError):
            timestamp = time.time()
        
        return UnifiedMessage(
            id=message.get("message_id"),
            listener=self.name,
            platform=self.PLATFORM_NAME,
            type=message_type,
            content=content,
            user_id=sender_id.get("union_id", "") or sender_id.get("user_id", ""),
            chat_id=message.get("chat_id", ""),
            thread_id=None,
            timestamp=timestamp,
            raw=raw
        )
    
    def _extract_post_content(self, content_data: dict) -> str:
        """
        提取富文本消息内容。
        
        Args:
            content_data: 富文本内容数据
        
        Returns:
            str: 提取的文本内容
        """
        text_parts = []
        
        def extract_text(node):
            if isinstance(node, dict):
                if "text" in node:
                    text_parts.append(node["text"])
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        extract_text(value)
            elif isinstance(node, list):
                for item in node:
                    extract_text(item)
        
        extract_text(content_data)
        return "".join(text_parts)
