#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
聊天会话映射模块

功能说明:
    - 管理 chat_id 到 session_id 的映射
    - 支持持久化存储，重启后恢复
    - 支持多 Agent 场景
"""

import os
import json
import threading
from datetime import datetime
from typing import Dict, Optional, Any
from dataclasses import dataclass, asdict
from loguru import logger


@dataclass
class ChatSessionInfo:
    """
    聊天会话信息
    
    Attributes:
        session_id: 会话 ID
        agent_id: Agent ID
        last_active: 最后活跃时间
        created_at: 创建时间
    """
    session_id: str
    agent_id: str = "default"
    last_active: str = ""
    created_at: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.last_active:
            self.last_active = datetime.now().isoformat()
    
    def touch(self):
        """更新最后活跃时间"""
        self.last_active = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatSessionInfo":
        return cls(
            session_id=data.get("session_id", ""),
            agent_id=data.get("agent_id", "default"),
            last_active=data.get("last_active", ""),
            created_at=data.get("created_at", ""),
        )


class ChatSessionMap:
    """
    聊天会话映射管理器
    
    管理 chat_id 到 session_id 的映射关系，支持持久化存储。
    """
    
    def __init__(
        self, 
        storage_path: str = "./sessions/chat_session_map.json",
        auto_save: bool = True
    ):
        self._storage_path = storage_path
        self._auto_save = auto_save
        self._lock = threading.RLock()
        self._map: Dict[str, ChatSessionInfo] = {}
        
        self._load()
        
        logger.info(f"[ChatSessionMap] 初始化完成: {storage_path}, 已加载 {len(self._map)} 个映射")
    
    def _load(self) -> None:
        """从文件加载映射"""
        if not os.path.exists(self._storage_path):
            return
        
        try:
            with open(self._storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for chat_id, info_dict in data.items():
                self._map[chat_id] = ChatSessionInfo.from_dict(info_dict)
            
            logger.debug(f"[ChatSessionMap] 加载映射: {len(self._map)} 个")
        except Exception as e:
            logger.error(f"[ChatSessionMap] 加载映射失败: {e}")
    
    def _save(self) -> bool:
        """保存映射到文件"""
        try:
            storage_dir = os.path.dirname(self._storage_path)
            if storage_dir:
                os.makedirs(storage_dir, exist_ok=True)
            
            data = {}
            for chat_id, info in self._map.items():
                data[chat_id] = info.to_dict()
            
            with open(self._storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            logger.error(f"[ChatSessionMap] 保存映射失败: {e}")
            return False
    
    def get(self, chat_id: str) -> Optional[ChatSessionInfo]:
        """获取聊天对应的会话信息"""
        with self._lock:
            return self._map.get(chat_id)
    
    def get_session_id(self, chat_id: str) -> Optional[str]:
        """获取聊天对应的会话 ID"""
        info = self.get(chat_id)
        return info.session_id if info else None
    
    def set_session(self, chat_id: str, session_id: str, agent_id: str = "default") -> None:
        """设置会话映射"""
        with self._lock:
            info = ChatSessionInfo(
                session_id=session_id,
                agent_id=agent_id
            )
            self._map[chat_id] = info
            
            if self._auto_save:
                self._save()
            
            logger.debug(f"[ChatSessionMap] 设置映射: {chat_id} -> {session_id}")
    
    def update(self, chat_id: str, session_id: str, agent_id: Optional[str] = None) -> bool:
        """更新会话映射"""
        with self._lock:
            if chat_id not in self._map:
                return False
            
            info = self._map[chat_id]
            info.session_id = session_id
            if agent_id:
                info.agent_id = agent_id
            info.touch()
            
            if self._auto_save:
                self._save()
            
            return True
    
    def delete(self, chat_id: str) -> bool:
        """删除会话映射"""
        with self._lock:
            if chat_id not in self._map:
                return False
            
            del self._map[chat_id]
            
            if self._auto_save:
                self._save()
            
            return True
    
    def exists(self, chat_id: str) -> bool:
        """检查映射是否存在"""
        return chat_id in self._map
    
    def count(self) -> int:
        """获取映射数量"""
        return len(self._map)
