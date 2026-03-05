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
"""

from agent.memory.memory_system import MemorySystem

__all__ = ["MemorySystem"]
