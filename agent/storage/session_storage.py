#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
会话存储管理模块

功能说明:
    - 管理会话的创建、加载、保存、删除
    - 支持会话过期清理
    - 支持会话元数据管理
    - 支持当前会话记录（重启后恢复）
    - 基于 TinyDB 实现

使用示例:
    storage = SessionStorage("./sessions/sessions.json")
    
    # 创建新会话
    session_id = storage.create_session()
    
    # 保存会话数据
    storage.save_session(session_id, {
        "history": [...],
        "system_prompt": "..."
    })
    
    # 加载会话
    data = storage.load_session(session_id)
    
    # 列出所有会话
    sessions = storage.list_sessions()
    
    # 获取/设置当前会话
    current = storage.get_current_session()
    storage.set_current_session(session_id)
"""

import os
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path
from loguru import logger

from .tinydb_storage import TinyDBStorage


class SessionConfig:
    """
    会话配置管理器。
    
    功能说明:
        - 管理当前激活的会话
        - 记录最近使用的会话列表
        - 支持重启后恢复会话
    
    配置文件结构:
        {
            "current_session": "sess_xxx",
            "last_accessed": "2026-02-21T18:00:00",
            "recent_sessions": ["sess_a", "sess_b"]
        }
    """
    
    def __init__(self, config_path: str):
        """
        初始化配置管理器。
        
        参数:
            config_path: 配置文件路径
        """
        self._config_path = config_path
        self._config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件。"""
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"加载会话配置失败: {e}，使用默认配置")
        
        return {
            "current_session": None,
            "last_accessed": None,
            "recent_sessions": []
        }
    
    def _save_config(self) -> bool:
        """保存配置文件。"""
        try:
            config_dir = os.path.dirname(self._config_path)
            if config_dir:
                os.makedirs(config_dir, exist_ok=True)
            
            with open(self._config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"保存会话配置失败: {e}")
            return False
    
    def get_current_session(self) -> Optional[str]:
        """
        获取当前会话ID。
        
        返回:
            Optional[str]: 当前会话ID，无则返回 None
        """
        return self._config.get("current_session")
    
    def set_current_session(self, session_id: Optional[str]) -> bool:
        """
        设置当前会话。
        
        参数:
            session_id: 会话ID，None 表示清除当前会话
        
        返回:
            bool: 设置是否成功
        """
        self._config["current_session"] = session_id
        self._config["last_accessed"] = datetime.now().isoformat()
        
        if session_id:
            self._add_to_recent(session_id)
        
        return self._save_config()
    
    def get_last_accessed(self) -> Optional[str]:
        """
        获取最后访问时间。
        
        返回:
            Optional[str]: ISO 格式的时间字符串
        """
        return self._config.get("last_accessed")
    
    def get_recent_sessions(self, limit: int = 10) -> List[str]:
        """
        获取最近使用的会话列表。
        
        参数:
            limit: 返回数量限制
        
        返回:
            List[str]: 会话ID列表
        """
        return self._config.get("recent_sessions", [])[:limit]
    
    def _add_to_recent(self, session_id: str, max_recent: int = 10) -> None:
        """
        添加会话到最近使用列表。
        
        参数:
            session_id: 会话ID
            max_recent: 最大保存数量
        """
        recent = self._config.get("recent_sessions", [])
        
        if session_id in recent:
            recent.remove(session_id)
        
        recent.insert(0, session_id)
        
        self._config["recent_sessions"] = recent[:max_recent]


class SessionStorage:
    """
    会话存储管理器。
    
    功能说明:
        - 会话创建与管理
        - 会话持久化存储
        - 会话过期清理
        - 会话元数据管理
        - 当前会话记录（重启后恢复）
    
    核心方法:
        - create_session: 创建新会话
        - load_session: 加载会话
        - save_session: 保存会话
        - delete_session: 删除会话
        - list_sessions: 列出所有会话
        - cleanup_expired: 清理过期会话
        - get_current_session: 获取当前会话
        - set_current_session: 设置当前会话
    
    配置项:
        - storage_path: 存储文件路径
        - max_sessions: 最大会话数
        - expire_days: 会话过期天数
    
    会话数据结构:
        {
            "history": [...],           # 对话历史
            "system_prompt": "...",     # 系统提示词
            "metadata": {
                "created_at": "...",    # 创建时间
                "updated_at": "...",    # 更新时间
                "message_count": 0,     # 消息数量
                "title": "..."          # 会话标题（可选）
            }
        }
    """
    
    def __init__(
        self,
        storage_path: str = "./sessions/sessions.json",
        max_sessions: int = 100,
        expire_days: int = 30
    ):
        """
        初始化会话存储管理器。
        
        参数:
            storage_path: 存储文件路径
            max_sessions: 最大会话数，默认100
            expire_days: 会话过期天数，默认30
        """
        self._storage = TinyDBStorage(storage_path)
        self._max_sessions = max_sessions
        self._expire_days = expire_days
        
        config_path = os.path.join(os.path.dirname(storage_path), "config.json")
        self._config = SessionConfig(config_path)
        
        logger.info(f"SessionStorage 初始化完成: {storage_path}, 最大会话数: {max_sessions}, 过期天数: {expire_days}")
    
    @staticmethod
    def generate_session_id() -> str:
        """
        生成唯一的会话ID。
        
        返回:
            str: 格式为 "sess_{timestamp}_{uuid}" 的会话ID
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_uuid = uuid.uuid4().hex[:8]
        return f"sess_{timestamp}_{short_uuid}"
    
    def create_session(self, title: Optional[str] = None) -> str:
        """
        创建新会话。
        
        参数:
            title: 会话标题（可选）
        
        返回:
            str: 新会话的ID
        """
        session_id = self.generate_session_id()
        now = datetime.now().isoformat()
        
        session_data = {
            "history": [],
            "system_prompt": "",
            "metadata": {
                "created_at": now,
                "updated_at": now,
                "message_count": 0,
                "title": title or f"会话 {session_id}"
            }
        }
        
        self._storage.save(session_id, session_data)
        logger.info(f"创建新会话: {session_id}")
        
        return session_id
    
    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        加载会话数据。
        
        参数:
            session_id: 会话ID
        
        返回:
            Optional[Dict]: 会话数据，不存在则返回 None
        """
        data = self._storage.load(session_id)
        if data:
            logger.debug(f"加载会话: {session_id}")
        else:
            logger.warning(f"会话不存在: {session_id}")
        return data
    
    def save_session(self, session_id: str, data: Dict[str, Any]) -> bool:
        """
        保存会话数据。
        
        参数:
            session_id: 会话ID
            data: 会话数据（应包含 history, system_prompt, metadata）
        
        返回:
            bool: 保存是否成功
        """
        if not self._storage.exists(session_id):
            logger.warning(f"会话不存在，将创建新会话: {session_id}")
        
        if "metadata" not in data:
            data["metadata"] = {}
        
        data["metadata"]["updated_at"] = datetime.now().isoformat()
        
        if "history" in data:
            data["metadata"]["message_count"] = len(data["history"])
        
        success = self._storage.save(session_id, data)
        if success:
            logger.debug(f"保存会话: {session_id}")
        return success
    
    def delete_session(self, session_id: str) -> bool:
        """
        删除会话。
        
        参数:
            session_id: 会话ID
        
        返回:
            bool: 删除是否成功
        """
        success = self._storage.delete(session_id)
        if success:
            logger.info(f"删除会话: {session_id}")
        return success
    
    def exists(self, session_id: str) -> bool:
        """
        检查会话是否存在。
        
        参数:
            session_id: 会话ID
        
        返回:
            bool: 会话是否存在
        """
        return self._storage.exists(session_id)
    
    def list_sessions(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        列出所有会话（按更新时间倒序）。
        
        参数:
            limit: 返回数量限制，默认50
            offset: 偏移量，默认0
        
        返回:
            List[Dict]: 会话列表，每项包含 session_id 和 metadata
        """
        all_keys = self._storage.list_all()
        sessions = []
        
        for key in all_keys:
            data = self._storage.load(key)
            if data:
                sessions.append({
                    "session_id": key,
                    "metadata": data.get("metadata", {})
                })
        
        sessions.sort(
            key=lambda x: x["metadata"].get("updated_at", ""),
            reverse=True
        )
        
        return sessions[offset:offset + limit]
    
    def get_session_count(self) -> int:
        """
        获取会话总数。
        
        返回:
            int: 会话总数
        """
        return self._storage.count()
    
    def cleanup_expired(self) -> int:
        """
        清理过期会话。
        
        返回:
            int: 清理的会话数量
        """
        expired_count = 0
        expire_threshold = datetime.now() - timedelta(days=self._expire_days)
        
        all_keys = self._storage.list_all()
        
        for key in all_keys:
            data = self._storage.load(key)
            if not data:
                continue
            
            metadata = data.get("metadata", {})
            updated_at_str = metadata.get("updated_at", "")
            
            if not updated_at_str:
                continue
            
            try:
                updated_at = datetime.fromisoformat(updated_at_str)
                if updated_at < expire_threshold:
                    self._storage.delete(key)
                    expired_count += 1
                    logger.info(f"清理过期会话: {key}")
            except ValueError:
                continue
        
        if expired_count > 0:
            logger.info(f"清理过期会话完成，共清理 {expired_count} 个")
        
        return expired_count
    
    def cleanup_oldest(self, keep_count: Optional[int] = None) -> int:
        """
        清理最旧的会话，保留指定数量。
        
        参数:
            keep_count: 保留数量，默认使用 max_sessions 配置
        
        返回:
            int: 清理的会话数量
        """
        keep = keep_count or self._max_sessions
        current_count = self._storage.count()
        
        if current_count <= keep:
            return 0
        
        sessions = self.list_sessions(limit=current_count)
        to_delete = sessions[keep:]
        
        deleted_count = 0
        for session in to_delete:
            if self._storage.delete(session["session_id"]):
                deleted_count += 1
        
        if deleted_count > 0:
            logger.info(f"清理最旧会话完成，共清理 {deleted_count} 个")
        
        return deleted_count
    
    def update_session_title(self, session_id: str, title: str) -> bool:
        """
        更新会话标题。
        
        参数:
            session_id: 会话ID
            title: 新标题
        
        返回:
            bool: 更新是否成功
        """
        data = self._storage.load(session_id)
        if not data:
            return False
        
        if "metadata" not in data:
            data["metadata"] = {}
        
        data["metadata"]["title"] = title
        data["metadata"]["updated_at"] = datetime.now().isoformat()
        
        return self._storage.save(session_id, data)
    
    def search_sessions(self, keyword: str) -> List[Dict[str, Any]]:
        """
        按关键词搜索会话（搜索标题和历史内容）。
        
        参数:
            keyword: 搜索关键词
        
        返回:
            List[Dict]: 匹配的会话列表
        """
        all_keys = self._storage.list_all()
        results = []
        
        for key in all_keys:
            data = self._storage.load(key)
            if not data:
                continue
            
            metadata = data.get("metadata", {})
            title = metadata.get("title", "")
            history = data.get("history", [])
            
            match_found = False
            
            if keyword.lower() in title.lower():
                match_found = True
            else:
                for msg in history:
                    content = msg.get("content", "")
                    if keyword.lower() in content.lower():
                        match_found = True
                        break
            
            if match_found:
                results.append({
                    "session_id": key,
                    "metadata": metadata
                })
        
        return results
    
    def get_current_session(self) -> Optional[str]:
        """
        获取当前会话ID。
        
        返回:
            Optional[str]: 当前会话ID，无则返回 None
        """
        return self._config.get_current_session()
    
    def set_current_session(self, session_id: Optional[str]) -> bool:
        """
        设置当前会话。
        
        参数:
            session_id: 会话ID，None 表示清除当前会话
        
        返回:
            bool: 设置是否成功
        """
        if session_id and not self.exists(session_id):
            logger.warning(f"会话不存在，无法设置为当前会话: {session_id}")
            return False
        
        success = self._config.set_current_session(session_id)
        if success and session_id:
            logger.info(f"设置当前会话: {session_id}")
        return success
    
    def get_recent_sessions(self, limit: int = 10) -> List[str]:
        """
        获取最近使用的会话列表。
        
        参数:
            limit: 返回数量限制
        
        返回:
            List[str]: 会话ID列表
        """
        return self._config.get_recent_sessions(limit)
    
    def get_first_message(self, session_id: str) -> Optional[str]:
        """
        获取会话的第一条用户消息（用于显示会话摘要）。
        
        参数:
            session_id: 会话ID
        
        返回:
            Optional[str]: 第一条用户消息，无则返回 None
        """
        data = self._storage.load(session_id)
        if not data:
            return None
        
        history = data.get("history", [])
        for msg in history:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                return content[:25] + "..." if len(content) > 25 else content
        
        return None
    
    def close(self) -> None:
        """关闭存储连接。"""
        self._storage.close()
        logger.debug("SessionStorage 连接已关闭")
    
    def __enter__(self):
        """支持上下文管理器。"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文时关闭连接。"""
        self.close()
