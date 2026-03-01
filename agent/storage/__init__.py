#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
存储模块

功能说明:
    - 提供统一的数据存储接口
    - 支持多种存储后端（TinyDB等）
    - 支持会话持久化

模块结构:
    - BaseStorage: 存储基类（抽象接口）
    - TinyDBStorage: TinyDB 存储实现
    - SessionStorage: 会话存储管理器

使用示例:
    from agent.storage import SessionStorage
    
    storage = SessionStorage("./sessions/sessions.json")
    session_id = storage.create_session(title="测试会话")
    storage.save_session(session_id, {"history": [...], "system_prompt": "..."})
"""

from .base_storage import BaseStorage
from .tinydb_storage import TinyDBStorage
from .session_storage import SessionStorage

__all__ = ["BaseStorage", "TinyDBStorage", "SessionStorage"]
