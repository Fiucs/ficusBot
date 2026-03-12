#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :models.py
# @Time      :2026/03/09
# @Author    :Ficus

"""
记忆系统数据模型

包含记忆条目、工具索引等数据模型定义。

Classes:
    MemoryEntry: 记忆条目数据模型
    ToolIndexEntry: 工具索引配置模型
    ToolIndex: 工具索引文件模型
    MemoryIndex: 记忆索引文件模型
"""

from typing import List, Optional
from datetime import datetime
import uuid

from pydantic import BaseModel, Field


class MemoryEntry(BaseModel):
    """
    记忆条目数据模型
    
    用于存储用户偏好、重要事实、对话记录等信息。
    
    Attributes:
        id: 记忆唯一标识符
        content: 记忆内容
        memory_type: 记忆类型（conversation/fact/preference/task/insight/document）
        importance: 重要性评分（1-10）
        tags: 标签列表
        created_at: 创建时间
    """
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    content: str
    memory_type: str = Field(default="conversation")
    importance: int = Field(default=5, ge=1, le=10)
    tags: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class ToolIndexEntry(BaseModel):
    """
    工具索引配置模型
    
    只存储控制配置，不存储完整工具定义。
    完整工具定义存储在向量数据库中。
    
    Attributes:
        name: 工具名称，唯一标识
        tool_type: 工具类型（builtin/mcp_server/skill）
        source: 技能来源路径（仅 skill 类型）
        mcp_server: MCP Server 名称（仅 mcp_server 类型）
        enabled: 是否启用（false 则从工具列表移除）
        add_to_memory: 是否加入记忆索引（true 则按需加载）
        query_count: 查询次数，用于热点统计
    """
    
    name: str
    tool_type: str = Field(default="skill")
    source: Optional[str] = Field(default=None)
    mcp_server: Optional[str] = Field(default=None)
    enabled: bool = Field(default=True)
    add_to_memory: bool = Field(default=True)
    query_count: int = Field(default=0)


class ToolIndex(BaseModel):
    """工具索引文件模型"""
    
    version: str = Field(default="1.0")
    updated_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    tools: List[ToolIndexEntry] = Field(default_factory=list)


class MemoryIndex(BaseModel):
    """记忆索引文件模型"""
    
    version: str = Field(default="1.0")
    updated_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    memories: List[MemoryEntry] = Field(default_factory=list)
