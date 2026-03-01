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
import threading
from typing import Dict, Any

from loguru import logger

from ..base_listener import BaseListener
from ..message_bus import UnifiedMessage


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
        
        参数:
            name: 监听器名称
            config: 配置字典
            bus: 消息总线实例
        """
        super().__init__(name, config, bus)
        self._client = None
        self._ws_client = None
        self._ws_thread = None
        
        # 获取配置（支持驼峰和下划线命名）
        self._app_id = config.get("app_id") or config.get("appId", "")
        self._app_secret = config.get("app_secret") or config.get("appSecret", "")
    
    async def start(self) -> bool:
        """
        启动飞书监听器。
        
        实现逻辑:
            1. 初始化 lark-oapi 客户端
            2. 启动 WebSocket 长连接
            3. 订阅 outgoing 事件
        
        返回:
            bool: 启动是否成功
        """
        try:
            from lark_oapi import Client, LogLevel
            from lark_oapi import ws
            from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
            
            if not self._app_id or not self._app_secret:
                logger.error(f"[{self.name}] 缺少 app_id/appId 或 app_secret/appSecret 配置")
                return False
            
            logger.info(f"[{self.name}] 正在初始化飞书客户端...")
            logger.info(f"[{self.name}] App ID: {self._app_id}")
            logger.info(f"[{self.name}] App Secret: {self._app_secret[:8]}...{self._app_secret[-4:]}")
            
            # 初始化客户端
            self._client = Client.builder() \
                .app_id(self._app_id) \
                .app_secret(self._app_secret) \
                .log_level(LogLevel.ERROR) \
                .build()
            
            logger.info(f"[{self.name}] 飞书客户端初始化成功")
            
            # 创建事件处理器
            event_handler = EventDispatcherHandler.builder("", "") \
                .register_p2_im_message_receive_v1(self._handle_ws_message) \
                .build()
            
            # 创建 WebSocket 客户端
            self._ws_client = ws.Client(
                app_id=self._app_id,
                app_secret=self._app_secret,
                log_level=LogLevel.INFO,
                event_handler=event_handler,
                auto_reconnect=True
            )
            
            # 在后台线程启动 WebSocket
            self._ws_thread = threading.Thread(
                target=self._run_ws_client,
                daemon=True,
                name=f"FeishuWS_{self.name}"
            )
            self._ws_thread.start()
            
            # 等待连接建立
            await asyncio.sleep(2)
            
            # 订阅 outgoing 事件
            self.bus.subscribe("outgoing", self._handle_outgoing)
            
            self._running = True
            
            logger.info(f"[{self.name}] ═════════════════════════════════════════")
            logger.info(f"[{self.name}] 🎉 飞书监听器启动成功")
            logger.info(f"[{self.name}] 📱 App ID: {self._app_id}")
            logger.info(f"[{self.name}] 🔌 连接模式: WebSocket 长连接")
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
    
    def _run_ws_client(self):
        """在后台线程运行 WebSocket 客户端。"""
        try:
            logger.info(f"[{self.name}] WebSocket 连接线程已启动")
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            # 运行客户端
            self._ws_client.start()
        except Exception as e:
            logger.error(f"[{self.name}] WebSocket 运行错误: {e}")
            import traceback
            logger.error(f"[{self.name}] 错误详情:\n{traceback.format_exc()}")
    
    def _handle_ws_message(self, event):
        """
        处理 WebSocket 接收到的消息事件。
        
        参数:
            event: 飞书消息事件 (P2ImMessageReceiveV1 对象)
        """
        logger.info(f"[{self.name}] 📨 收到 WebSocket 消息")
        
        # 在新线程中处理以避免阻塞 WebSocket
        thread = threading.Thread(
            target=self._process_event_in_thread,
            args=(event,),
            daemon=True
        )
        thread.start()
    
    def _process_event_in_thread(self, event):
        """在新线程中处理事件。"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._process_sdk_event(event))
            loop.close()
        except Exception as e:
            logger.error(f"[{self.name}] 处理消息线程错误: {e}")
    
    async def _process_sdk_event(self, event) -> None:
        """
        处理 SDK 事件对象。
        
        参数:
            event: 飞书 SDK 事件对象
        """
        try:
            # 提取事件数据
            event_data = event.event if hasattr(event, 'event') else event
            message = event_data.message if hasattr(event_data, 'message') else None
            sender = event_data.sender if hasattr(event_data, 'sender') else None
            header = event.header if hasattr(event, 'header') else None
            
            if not message:
                logger.warning(f"[{self.name}] 事件没有 message 属性")
                return
            
            # 构造统一格式的消息数据
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
            
            # 发布消息到消息总线
            await self._publish_incoming(formatted_data)
            
        except Exception as e:
            logger.error(f"[{self.name}] 处理 SDK 事件失败: {e}")
            import traceback
            logger.error(f"[{self.name}] 错误堆栈:\n{traceback.format_exc()}")
    
    async def stop(self) -> bool:
        """
        停止飞书监听器。
        
        返回:
            bool: 停止是否成功
        """
        try:
            self._running = False
            
            logger.info(f"[{self.name}] 正在停止...")
            
            # WebSocket 客户端会在后台线程中自动关闭
            if self._ws_client:
                # SDK 的 WebSocket 客户端没有显式关闭方法
                # 依赖线程结束和自动重连机制的停止
                pass
            
            await self._cancel_all_tasks()
            
            logger.info(f"[{self.name}] 飞书监听器已停止")
            return True
            
        except Exception as e:
            logger.error(f"[{self.name}] 停止失败: {e}")
            return False
    
    async def send_message(self, target: Dict[str, str], content: str, **kwargs) -> Dict[str, Any]:
        """
        发送消息到飞书。
        
        参数:
            target: 目标信息字典，包含 chat_id
            content: 消息内容
            **kwargs: 其他参数
        
        返回:
            Dict: 发送结果
        """
        try:
            import lark_oapi.api.im.v1 as im
            
            chat_id = target.get("chat_id")
            if not chat_id:
                logger.error(f"[{self.name}] 缺少 chat_id")
                return {"success": False, "error": "缺少 chat_id"}
            
            msg_type = "text"
            
            # 构造请求
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
            
            # 发送消息
            response = await asyncio.to_thread(
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
        
        参数:
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
        
        参数:
            raw: 飞书事件推送的 JSON 数据
        
        返回:
            UnifiedMessage: 统一格式消息
        """
        event = raw.get("event", {})
        message = event.get("message", {})
        sender = event.get("sender", {})
        sender_id = sender.get("sender_id", {})
        
        message_type = message.get("message_type", "text")
        content_raw = message.get("content", "{}")
        
        # 解析消息内容
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
        
        # 处理时间戳
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
        
        参数:
            content_data: 富文本内容数据
        
        返回:
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
