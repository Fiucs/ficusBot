#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :__init__.py
# @Time      :2026/03/05
# @Author    :Ficus

"""
记忆系统模块

提供 Agent 长记忆存储和语义搜索能力：
- 持久化记忆：存储重要对话内容、用户偏好、任务结果等
- 语义搜索：通过自然语言查询相关记忆和工具
- 工具库管理：自动索引所有可用工具，支持语义检索

模块结构:
    - MemorySystem: 记忆系统主入口
    - EmbeddingService: 嵌入服务
    - ToolStore: 工具存储
"""

from agent.memory.memory_system import MemorySystem
from agent.memory.embedding_service import EmbeddingService
from agent.memory.tool_store import ToolStore

__all__ = ["MemorySystem", "EmbeddingService", "ToolStore"]
