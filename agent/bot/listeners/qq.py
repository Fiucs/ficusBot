#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :qq.py
# @Time      :2026/02/22
# @Author    :Ficus

"""
QQ 监听器模块（使用统一连接架构）

功能说明:
    - 使用 WebSocket 连接到 go-cqhttp 或 OneBot 协议实现
    - 基于统一连接管理架构，简化实现
    - 支持接收和发送消息
    - 将 QQ 消息转换为统一格式

配置项:
    - ws_url: WebSocket 连接地址（如 ws://localhost:3001）
    - access_token: 访问令牌（可选）

依赖:
    pip install websockets

参考:
    - go-cqhttp: https://docs.go-cqhttp.org/
    - OneBot 协议: https://github.com/botuniverse/onebot-11
"""

import json
import time
from typing import Dict, Any

from loguru import logger

from ..base_listener import BaseListener
from ..message_bus import UnifiedMessage
from ..connection import WebSocketConnection


class QQListener(BaseListener):
    """
    QQ 监听器
    
    使用 WebSocket 连接到 go-cqhttp 或兼容 OneBot 协议的服务端。
    基于统一连接管理架构，自动处理重连、心跳等底层逻辑。
    
    功能说明:
        - 基于 WebSocketConnection 统一连接管理
        - 自动重连和心跳保活
        - 支持私聊和群聊消息
        - 支持发送文本消息
    
    核心方法:
        - start: 启动监听器
        - stop: 停止监听器
        - send_message: 发送消息
        - _convert_to_unified: 转换消息格式
    
    配置示例:
        {
            "ws_url": "ws://localhost:3001",
            "access_token": "your_token"
        }
    """
    
    PLATFORM_NAME = "qq"
    PLATFORM_DISPLAY_NAME = "QQ"
    
    def __init__(self, name: str, config: Dict[str, Any], bus):
        """
        初始化 QQ 监听器。
        
        参数:
            name: 监听器名称
            config: 配置字典，包含 ws_url 和可选的 access_token
            bus: 消息总线实例
        """
        super().__init__(name, config, bus)
        self._ws_url = config.get("ws_url", "")
        self._access_token = config.get("access_token", "")
        self._connection: WebSocketConnection = None
    
    async def start(self) -> bool:
        """
        启动 QQ 监听器。
        
        实现逻辑:
            1. 创建 WebSocketConnection 实例
            2. 设置消息回调
            3. 启动连接
            4. 订阅 outgoing 事件
        
        返回:
            bool: 启动是否成功
        """
        if not self._ws_url:
            logger.error(f"[{self.name}] 缺少 ws_url 配置")
            return False
        
        try:
            logger.info(f"[{self.name}] 正在启动 QQ 监听器...")
            logger.info(f"[{self.name}] WebSocket URL: {self._ws_url}")
            
            # 创建统一连接实例
            self._connection = WebSocketConnection(
                url=self._ws_url,
                name=f"{self.name}_ws",
                access_token=self._access_token,
                heartbeat_interval=30,
                reconnect_interval=5,
                reconnect_enabled=True
            )
            
            # 设置回调
            self._connection.on_message = self._handle_ws_message
            self._connection.on_connect = lambda: logger.info(f"[{self.name}] ✅ WebSocket 已连接")
            self._connection.on_disconnect = lambda: logger.warning(f"[{self.name}] 🔌 WebSocket 已断开")
            self._connection.on_error = lambda e: logger.error(f"[{self.name}] 连接错误: {e}")
            
            # 启动连接
            success = await self._connection.connect()
            if not success:
                logger.error(f"[{self.name}] 连接失败")
                return False
            
            # 订阅 outgoing 事件
            self.bus.subscribe("outgoing", self._handle_outgoing)
            
            self._running = True
            
            logger.info(f"[{self.name}] ═════════════════════════════════════════")
            logger.info(f"[{self.name}] 🎉 QQ 监听器启动成功")
            logger.info(f"[{self.name}] 🔌 连接模式: WebSocket（统一连接架构）")
            logger.info(f"[{self.name}] 🔗 服务器: {self._ws_url}")
            logger.info(f"[{self.name}] ═════════════════════════════════════════")
            
            return True
            
        except Exception as e:
            logger.error(f"[{self.name}] 启动失败: {e}")
            import traceback
            logger.error(f"[{self.name}] 错误堆栈:\n{traceback.format_exc()}")
            return False
    
    async def stop(self) -> bool:
        """
        停止 QQ 监听器。
        
        返回:
            bool: 停止是否成功
        """
        logger.info(f"[{self.name}] 正在停止...")
        self._running = False
        
        if self._connection:
            await self._connection.disconnect()
            self._connection = None
        
        await super().stop()
        logger.info(f"[{self.name}] 已停止")
        return True
    
    async def _handle_ws_message(self, data) -> None:
        """
        处理 WebSocket 接收到的消息。
        
        参数:
            data: 解析后的消息数据（字典或字符串）
        """
        try:
            # 确保是字典
            if isinstance(data, str):
                data = json.loads(data)
            
            # 处理元事件（心跳、生命周期等）
            if data.get("post_type") == "meta_event":
                return
            
            # 处理消息事件
            if data.get("post_type") == "message":
                logger.info(f"[{self.name}] 📨 收到消息")
                await self._publish_incoming(data)
                
        except json.JSONDecodeError:
            logger.warning(f"[{self.name}] 收到非 JSON 消息: {str(data)[:100]}")
        except Exception as e:
            logger.error(f"[{self.name}] 处理消息失败: {e}")
    
    async def send_message(self, target: Dict[str, str], content: str, **kwargs) -> Dict[str, Any]:
        """
        发送消息到 QQ。
        
        参数:
            target: 目标信息字典，包含 chat_id
            content: 消息内容
            **kwargs: 其他参数
        
        返回:
            Dict: 发送结果
        """
        if not self._connection or not self._connection.is_connected:
            logger.error(f"[{self.name}] WebSocket 未连接")
            return {"success": False, "error": "WebSocket 未连接"}
        
        try:
            chat_id = target.get("chat_id", "")
            
            # 判断是私聊还是群聊
            if chat_id.startswith("group_"):
                # 群聊
                group_id = chat_id.replace("group_", "")
                msg = {
                    "action": "send_group_msg",
                    "params": {
                        "group_id": int(group_id),
                        "message": content
                    }
                }
            else:
                # 私聊
                msg = {
                    "action": "send_private_msg",
                    "params": {
                        "user_id": int(chat_id),
                        "message": content
                    }
                }
            
            success = await self._connection.send(msg)
            if success:
                logger.info(f"[{self.name}] 消息已发送")
                return {"success": True}
            else:
                return {"success": False, "error": "发送失败"}
            
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
        
        target = {"chat_id": data.get("chat_id")}
        await self.send_message(target, data.get("content", ""))
    
    async def _convert_to_unified(self, raw: Dict[str, Any]) -> UnifiedMessage:
        """
        将 QQ 消息转换为统一格式。
        
        参数:
            raw: QQ 原始消息
        
        返回:
            UnifiedMessage: 统一格式的消息
        """
        message_type = raw.get("message_type", "")
        
        if message_type == "private":
            chat_id = str(raw.get("user_id", ""))
        elif message_type == "group":
            chat_id = f"group_{raw.get('group_id', '')}"
        else:
            chat_id = ""
        
        # 提取消息内容
        messages = raw.get("message", [])
        content = ""
        
        if isinstance(messages, list):
            for msg in messages:
                if msg.get("type") == "text":
                    content += msg.get("data", {}).get("text", "")
                elif msg.get("type") == "at":
                    content += f"@{msg.get('data', {}).get('qq', '')} "
                elif msg.get("type") == "image":
                    content += "[图片]"
                elif msg.get("type") == "face":
                    content += "[表情]"
        elif isinstance(messages, str):
            content = messages
        
        return UnifiedMessage(
            id=str(raw.get("message_id", "")),
            listener=self.name,
            platform=self.PLATFORM_NAME,
            type=message_type,
            content=content,
            user_id=str(raw.get("user_id", "")),
            chat_id=chat_id,
            thread_id=None,
            timestamp=raw.get("time", int(time.time())),
            raw=raw
        )
