#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
聊天会话映射模块

功能说明:
    - 管理 chat_id 到 session_id 的映射
    - 支持持久化存储，重启后恢复
    - 支持多 Agent 场景

存储结构:
    {
        "feishu:ou_xxx": {
            "session_id": "sess_20260302_xxx",
            "agent_id": "default",
            "last_active": "2026-03-02T15:00:00",
            "created_at": "2026-03-02T14:00:00"
        },
        "telegram:123456": {
            "session_id": "sess_20260302_yyy",
            "agent_id": "default",
            "last_active": "2026-03-02T14:30:00",
            "created_at": "2026-03-02T13:00:00"
        }
    }

使用示例:
    from agent.server.session_map import ChatSessionMap
    
    session_map = ChatSessionMap("./sessions/chat_session_map.json")
    
    # 获取或创建会话
    session_id = session_map.get_or_create("feishu:ou_xxx", "default")
    
    # 更新会话
    session_map.update("feishu:ou_xxx", "sess_new_xxx", "coder")
    
    # 删除映射
    session_map.delete("feishu:ou_xxx")
"""
import os
import json
import threading
from datetime import datetime
from typing import Dict, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path
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
    
    功能说明:
        - chat_id 与 session_id 的映射管理
        - 持久化存储，重启后自动恢复
        - 支持多 Agent 场景
        - 自动清理过期映射
    
    核心方法:
        - get_or_create: 获取或创建会话映射
        - update: 更新会话映射
        - delete: 删除会话映射
        - get: 获取会话信息
    
    使用示例:
        session_map = ChatSessionMap("./sessions/chat_session_map.json")
        
        # 获取或创建会话（自动持久化）
        session_id = session_map.get_or_create("feishu:ou_xxx", "default")
        
        # 更新会话
        session_map.update("feishu:ou_xxx", "sess_new_xxx", "coder")
        
        # 删除映射
        session_map.delete("feishu:ou_xxx")
    """
    
    def __init__(
        self, 
        storage_path: str = "./sessions/chat_session_map.json",
        auto_save: bool = True
    ):
        """
        初始化聊天会话映射管理器。
        
        Args:
            storage_path: 存储文件路径
            auto_save: 是否自动保存（每次更新后自动持久化）
        """
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
        """
        获取聊天对应的会话信息。
        
        Args:
            chat_id: 聊天标识（格式: platform:user_id）
        
        Returns:
            ChatSessionInfo 或 None
        """
        with self._lock:
            return self._map.get(chat_id)
    
    def get_session_id(self, chat_id: str) -> Optional[str]:
        """
        获取聊天对应的会话 ID。
        
        Args:
            chat_id: 聊天标识
        
        Returns:
            session_id 或 None
        """
        info = self.get(chat_id)
        return info.session_id if info else None
    
    def get_or_create(
        self, 
        chat_id: str, 
        agent_id: str = "default",
        session_id: Optional[str] = None
    ) -> str:
        """
        获取或创建会话映射。
        
        如果 chat_id 已有映射，返回已有的 session_id。
        否则创建新映射并持久化。
        
        Args:
            chat_id: 聊天标识
            agent_id: Agent ID
            session_id: 指定的会话 ID（可选，不指定则自动生成）
        
        Returns:
            str: session_id
        """
        with self._lock:
            if chat_id in self._map:
                info = self._map[chat_id]
                info.touch()
                if self._auto_save:
                    self._save()
                return info.session_id
            
            if not session_id:
                from agent.storage import SessionStorage
                session_id = SessionStorage.generate_session_id()
            
            info = ChatSessionInfo(
                session_id=session_id,
                agent_id=agent_id
            )
            
            self._map[chat_id] = info
            
            if self._auto_save:
                self._save()
            
            logger.debug(f"[ChatSessionMap] 创建映射: {chat_id} -> {session_id}")
            
            return session_id
    
    def update(
        self, 
        chat_id: str, 
        session_id: str, 
        agent_id: Optional[str] = None
    ) -> bool:
        """
        更新会话映射。
        
        Args:
            chat_id: 聊天标识
            session_id: 新的会话 ID
            agent_id: 新的 Agent ID（可选）
        
        Returns:
            bool: 是否更新成功
        """
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
            
            logger.debug(f"[ChatSessionMap] 更新映射: {chat_id} -> {session_id}")
            
            return True
    
    def set_session(self, chat_id: str, session_id: str, agent_id: str = "default") -> None:
        """
        设置会话映射（不存在则创建）。
        
        Args:
            chat_id: 聊天标识
            session_id: 会话 ID
            agent_id: Agent ID
        """
        with self._lock:
            info = ChatSessionInfo(
                session_id=session_id,
                agent_id=agent_id
            )
            self._map[chat_id] = info
            
            if self._auto_save:
                self._save()
            
            logger.debug(f"[ChatSessionMap] 设置映射: {chat_id} -> {session_id}")
    
    def delete(self, chat_id: str) -> bool:
        """
        删除会话映射。
        
        Args:
            chat_id: 聊天标识
        
        Returns:
            bool: 是否删除成功
        """
        with self._lock:
            if chat_id not in self._map:
                return False
            
            del self._map[chat_id]
            
            if self._auto_save:
                self._save()
            
            logger.debug(f"[ChatSessionMap] 删除映射: {chat_id}")
            
            return True
    
    def exists(self, chat_id: str) -> bool:
        """检查映射是否存在"""
        return chat_id in self._map
    
    def list_all(self) -> Dict[str, ChatSessionInfo]:
        """获取所有映射"""
        with self._lock:
            return self._map.copy()
    
    def count(self) -> int:
        """获取映射数量"""
        return len(self._map)
    
    def clear(self) -> None:
        """清空所有映射"""
        with self._lock:
            self._map.clear()
            if self._auto_save:
                self._save()
    
    def cleanup_inactive(self, days: int = 30) -> int:
        """
        清理长时间未活跃的映射。
        
        Args:
            days: 未活跃天数阈值
        
        Returns:
            int: 清理的数量
        """
        from datetime import timedelta
        
        threshold = datetime.now() - timedelta(days=days)
        cleaned = 0
        
        with self._lock:
            to_delete = []
            
            for chat_id, info in self._map.items():
                try:
                    last_active = datetime.fromisoformat(info.last_active)
                    if last_active < threshold:
                        to_delete.append(chat_id)
                except Exception:
                    to_delete.append(chat_id)
            
            for chat_id in to_delete:
                del self._map[chat_id]
                cleaned += 1
            
            if cleaned > 0 and self._auto_save:
                self._save()
            
            logger.info(f"[ChatSessionMap] 清理过期映射: {cleaned} 个")
        
        return cleaned
