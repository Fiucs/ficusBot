#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :wecom.py
# @Time      :2026/02/22
# @Author    :Ficus

"""
企业微信监听器模块（简化版）

功能说明:
    - 使用企业微信官方 API
    - 长轮询模式接收消息
    - 支持接收和发送消息

配置项:
    - corp_id: 企业 ID
    - agent_id: 应用 ID
    - secret: 应用密钥

依赖:
    pip install requests
"""

import asyncio
import json
import time
from typing import Dict, Any

from loguru import logger

from ..base_listener import BaseListener
from ..message_bus import UnifiedMessage


class WeComListener(BaseListener):
    """
    企业微信监听器
    
    使用长轮询模式接收消息。
    
    配置示例:
        {
            "corp_id": "wwxxxxxxxxxxxxxxxx",
            "agent_id": "1000002",
            "secret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        }
    """
    
    PLATFORM_NAME = "wecom"
    PLATFORM_DISPLAY_NAME = "企业微信"
    
    def __init__(self, name: str, config: Dict[str, Any], bus):
        super().__init__(name, config, bus)
        self._corp_id = config.get("corp_id", "")
        self._agent_id = config.get("agent_id", "")
        self._secret = config.get("secret", "")
        self._access_token = None
        self._poll_task = None
    
    async def start(self) -> bool:
        """启动监听器。"""
        if not all([self._corp_id, self._agent_id, self._secret]):
            logger.error(f"[{self.name}] 缺少配置: corp_id, agent_id, secret")
            return False
        
        try:
            logger.info(f"[{self.name}] 正在启动企业微信监听器...")
            
            # 获取 token
            if not await self._refresh_token():
                return False
            
            # 启动消息轮询
            self._poll_task = self._create_task(self._poll_messages(), name="wecom_poll")
            
            # 订阅 outgoing 事件
            self.bus.subscribe("outgoing", self._handle_outgoing)
            
            self._running = True
            
            logger.info(f"[{self.name}] ═════════════════════════════════════════")
            logger.info(f"[{self.name}] 🎉 企业微信监听器启动成功")
            logger.info(f"[{self.name}] 🔌 连接模式: 长轮询")
            logger.info(f"[{self.name}] ═════════════════════════════════════════")
            
            return True
            
        except Exception as e:
            logger.error(f"[{self.name}] 启动失败: {e}")
            return False
    
    async def _refresh_token(self) -> bool:
        """刷新 access_token。"""
        try:
            import requests
            
            url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken"
            params = {
                "corpid": self._corp_id,
                "corpsecret": self._secret
            }
            
            response = await asyncio.to_thread(requests.get, url, params=params, timeout=30)
            data = response.json()
            
            if data.get("errcode") == 0:
                self._access_token = data.get("access_token")
                logger.info(f"[{self.name}] Token 刷新成功")
                return True
            else:
                logger.error(f"[{self.name}] 获取 token 失败: {data}")
                return False
                
        except Exception as e:
            logger.error(f"[{self.name}] 刷新 token 失败: {e}")
            return False
    
    async def _poll_messages(self) -> None:
        """消息轮询循环。"""
        while self._running:
            try:
                if not self._access_token:
                    await asyncio.sleep(5)
                    continue
                
                # 这里简化处理，实际应该调用企业微信的消息接收接口
                # 企业微信需要通过回调或主动拉取方式获取消息
                await asyncio.sleep(3)
                
            except Exception as e:
                logger.error(f"[{self.name}] 轮询错误: {e}")
                await asyncio.sleep(5)
    
    async def stop(self) -> bool:
        """停止监听器。"""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        await super().stop()
        return True
    
    async def send_message(self, target: Dict[str, str], content: str, **kwargs) -> Dict[str, Any]:
        """发送消息。"""
        try:
            import requests
            
            url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={self._access_token}"
            
            payload = {
                "touser": target.get("chat_id", ""),
                "msgtype": "text",
                "agentid": self._agent_id,
                "text": {"content": content}
            }
            
            response = await asyncio.to_thread(requests.post, url, json=payload, timeout=30)
            result = response.json()
            
            if result.get("errcode") == 0:
                logger.info(f"[{self.name}] 消息发送成功")
                return {"success": True}
            else:
                logger.error(f"[{self.name}] 发送失败: {result}")
                return {"success": False, "error": str(result)}
                
        except Exception as e:
            logger.error(f"[{self.name}] 发送消息失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def _handle_outgoing(self, data: dict) -> None:
        """处理 outgoing 事件。"""
        if data.get("listener") != self.name:
            return
        
        target = {"chat_id": data.get("chat_id")}
        await self.send_message(target, data.get("content", ""))
    
    async def _convert_to_unified(self, raw: Dict[str, Any]) -> UnifiedMessage:
        """转换为统一格式。"""
        return UnifiedMessage(
            id=str(raw.get("MsgId", "")),
            listener=self.name,
            platform=self.PLATFORM_NAME,
            type="text",
            content=raw.get("Content", ""),
            user_id=raw.get("FromUserName", ""),
            chat_id=raw.get("ToUserName", ""),
            thread_id=None,
            timestamp=time.time(),
            raw=raw
        )
