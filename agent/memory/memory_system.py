#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :memory_system.py
# @Time      :2026/03/05
# @Author    :Ficus

"""
记忆系统 - 统一接口

整合向量存储、嵌入服务、JSON索引管理于一体。

核心方法:
    process_tools: 处理工具列表（根据索引文件过滤）
    search_tools: 搜索记忆索引中的工具（单个查询）
    search_tools_batch: 批量搜索记忆索引中的工具（支持多个查询，自动去重）
    save: 保存单条记忆
    save_batch: 批量保存记忆（高性能版本）
    search: 统一搜索（记忆+工具）
    compact: 压缩数据库表，减少碎片

设计原则:
    - 系统先加载所有工具
    - 根据索引文件过滤和分类工具
    - enabled=false 移除工具
    - add_to_memory=true 存入记忆索引并移除
    - add_to_memory=false 保留在工具列表
"""

import os
import uuid
import json
import json5
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

from loguru import logger

from agent.memory.embedding_service import EmbeddingService
from agent.memory.tool_store import ToolStore
from agent.memory.memory_store import MemoryStore


class MemorySystem:
    """
    记忆系统 - 统一接口
    
    整合向量存储、嵌入服务、JSON索引管理于一体。
    
    核心方法:
        process_tools: 处理工具列表（根据索引文件过滤）
        search_tools: 搜索记忆索引中的工具（单个查询）
        search_tools_batch: 批量搜索记忆索引中的工具（支持多个查询，自动去重）
        save: 保存单条记忆
        save_batch: 批量保存记忆（高性能版本）
        search: 统一搜索（记忆+工具）
        compact: 压缩数据库表，减少碎片
    
    设计原则:
        - 系统先加载所有工具
        - 根据索引文件过滤和分类工具
        - enabled=false 移除工具
        - add_to_memory=true 存入记忆索引并移除
        - add_to_memory=false 保留在工具列表
    
    Attributes:
        config: 配置字典
        db_path: 向量数据库路径
        index_path: 索引文件路径
        hot_threshold: 热点工具阈值
        db: LanceDB 连接
        memories_table: 记忆表
        tools_table: 工具表
        memories_schema: 记忆表 Schema
        tools_schema: 工具表 Schema
        embedding_service: 嵌入服务实例
        tool_store: 工具存储实例
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化记忆系统
        
        Args:
            config: 配置字典，包含以下键：
                - db_path: 向量数据库路径（默认 ./workspace/vector_db）
                - index_path: 索引文件路径（默认 ./workspace/memory_index）
                - hot_threshold: 热点工具阈值（默认 10）
                - embedding: 嵌入服务配置
        """
        self.config = config
        
        workspace_root = self._get_workspace_root()
        
        self.db_path = self._resolve_path(config.get("db_path", "./workspace/vector_db"), workspace_root)
        self.index_path = Path(self._resolve_path(config.get("index_path", "./workspace/memory_index"), workspace_root))
        self.hot_threshold = config.get("hot_threshold", 10)
        self.hot_tool_limit = config.get("hot_tool_limit", 5)
        
        self.index_path.mkdir(parents=True, exist_ok=True)
        
        self._init_index_files()
        self.embedding_service = EmbeddingService(config.get("embedding", {}), workspace_root)
        self._init_db()
        self._init_tool_store()
        self._init_memory_store()
        
        logger.info(f"记忆系统初始化完成: db={self.db_path}, index={self.index_path}")
    
    def _get_workspace_root(self) -> str:
        """获取工作区根目录"""
        try:
            from agent.config.configloader import GLOBAL_CONFIG
            return GLOBAL_CONFIG.get("workspace_root", ".")
        except ImportError:
            return "."
    
    def _resolve_path(self, path: str, workspace_root: str) -> str:
        """
        解析路径，支持变量替换
        
        支持：
        - {workspace_root} 变量替换
        - 相对路径转换为绝对路径
        
        Args:
            path: 原始路径
            workspace_root: 工作区根目录
        
        Returns:
            解析后的绝对路径
        """
        if not path:
            return path
        
        path = path.replace("{workspace_root}", workspace_root)
        
        if not os.path.isabs(path):
            path = os.path.abspath(path)
        
        return path
    
    def _init_index_files(self):
        """初始化索引文件（如果不存在则创建，使用 JSON5 格式支持注释）"""
        tool_index_file = self.index_path / "tool_index.json"
        memory_index_file = self.index_path / "memory_index.json"
        
        if not tool_index_file.exists():
            tool_index_content = '''{
    // ==========================================
    // 工具索引文件 - 管理所有工具的注册和配置
    // ==========================================
    // 
    // 字段说明：
    //   name: 工具名称（唯一标识）
    //   tool_type: 工具类型 - builtin(内置) / mcp_server(MCP服务) / skill(技能)
    //   source: 工具来源路径（仅skill类型）
    //   mcp_server: MCP服务名称（仅mcp_server类型）
    //   enabled: 是否启用（false则从工具列表移除）
    //   add_to_memory: 是否加入记忆索引（true则按需加载，减少token消耗）
    //   query_count: 查询次数（达到hot_threshold自动转为始终加载）
    //
    // ==========================================
    
    "version": "1.0",
    "updated_at": "''' + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + '''",
    "tools": [
        // 示例：技能工具
        // {
        //     "name": "web-search",
        //     "tool_type": "skill",
        //     "source": "skills/web-search.md",
        //     "enabled": true,
        //     "add_to_memory": true,
        //     "query_count": 0
        // },
        // 
        // 示例：MCP服务工具
        // {
        //     "name": "filesystem",
        //     "tool_type": "mcp_server",
        //     "mcp_server": "filesystem-server",
        //     "enabled": true,
        //     "add_to_memory": false,
        //     "query_count": 5
        // },
        // 
        // 示例：内置工具
        // {
        //     "name": "file_read",
        //     "tool_type": "builtin",
        //     "enabled": true,
        //     "add_to_memory": false,
        //     "query_count": 15
        // },
        // 
        // 示例：禁用的工具
        // {
        //     "name": "deprecated-tool",
        //     "tool_type": "skill",
        //     "enabled": false,
        //     "add_to_memory": true,
        //     "query_count": 0
        // }
    ]
}'''
            with open(tool_index_file, "w", encoding="utf-8") as f:
                f.write(tool_index_content)
            logger.info(f"创建工具索引文件: {tool_index_file}")
        
#         if not memory_index_file.exists():
#             memory_index_content = '''{
#     // ==========================================
#     // 记忆索引文件 - 存储用户的长期记忆
#     // ==========================================
#     // 
#     // 字段说明：
#     //   id: 记忆唯一标识（8位UUID）
#     //   content: 记忆内容
#     //   memory_type: 记忆类型
#     //     - conversation: 对话记录
#     //     - fact: 事实信息
#     //     - preference: 用户偏好
#     //     - task: 任务结果
#     //     - insight: 洞察总结
#     //     - document: 文档摘要
#     //   importance: 重要性评分（1-10，默认5）
#     //   tags: 标签列表（用于分类和检索）
#     //   created_at: 创建时间
#     //
#     // ==========================================
    
#     "version": "1.0",
#     "updated_at": "''' + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + '''",
#     "memories": [
#         // 示例：用户偏好
#         // {
#         //     "id": "pref001",
#         //     "content": "用户偏好使用中文交流，工作语言为Python",
#         //     "memory_type": "preference",
#         //     "importance": 8,
#         //     "tags": ["language", "programming"],
#         //     "created_at": "2026-03-05 10:00:00"
#         // },
#         // 
#         // 示例：事实信息
#         // {
#         //     "id": "fact001",
#         //     "content": "项目使用FastAPI框架，数据库为PostgreSQL",
#         //     "memory_type": "fact",
#         //     "importance": 7,
#         //     "tags": ["project", "tech_stack"],
#         //     "created_at": "2026-03-05 10:30:00"
#         // },
#         // 
#         // 示例：任务结果
#         // {
#         //     "id": "task001",
#         //     "content": "已完成用户认证模块的开发，使用JWT令牌",
#         //     "memory_type": "task",
#         //     "importance": 6,
#         //     "tags": ["completed", "auth"],
#         //     "created_at": "2026-03-05 14:00:00"
#         // }
#     ]
# }'''


            # with open(memory_index_file, "w", encoding="utf-8") as f:
            #     f.write(memory_index_content)
            # logger.info(f"创建记忆索引文件: {memory_index_file}")
    
    def _init_db(self):
        """初始化数据库连接和表"""
        db_path = Path(self.db_path)
        db_path.mkdir(parents=True, exist_ok=True)
        
        try:
            import lancedb
            import pyarrow as pa
            
            embedding_dim = self.embedding_service.get_embedding_dim()
            
            logger.info(f"连接向量数据库: {db_path}, 嵌入维度: {embedding_dim}")
            self.db = lancedb.connect(self.db_path)
            
            self.memories_schema = pa.schema([
                pa.field("id", pa.string()),
                pa.field("content", pa.string()),
                pa.field("embedding", pa.list_(pa.float32(), list_size=embedding_dim)),
                pa.field("memory_type", pa.string()),
                pa.field("importance", pa.int64()),
                pa.field("tags", pa.list_(pa.string())),
                pa.field("created_at", pa.string())
            ])
            
            self.tools_schema = pa.schema([
                pa.field("id", pa.string()),
                pa.field("name", pa.string()),
                pa.field("tool_type", pa.string()),
                pa.field("embedding", pa.list_(pa.float32(), list_size=embedding_dim)),
                pa.field("tool_definition", pa.string()),
                pa.field("query_count", pa.int64())
            ])
            
            table_names = self.db.table_names()
            
            if "memories" not in table_names:
                self.memories_table = self.db.create_table("memories", schema=self.memories_schema, mode="overwrite")
                logger.info("创建 memories 表")
            else:
                self.memories_table = self.db.open_table("memories")
                existing_dim = self._get_table_embedding_dim(self.memories_table)
                if existing_dim != embedding_dim:
                    logger.warning(f"memories 表维度不匹配 (现有: {existing_dim}, 需要: {embedding_dim})")
                    self._migrate_memories_table(embedding_dim, self.memories_schema)
            
            if "tools" not in table_names:
                self.tools_table = self.db.create_table("tools", schema=self.tools_schema, mode="overwrite")
                logger.info("创建 tools 表")
            else:
                self.tools_table = self.db.open_table("tools")
                existing_dim = self._get_table_embedding_dim(self.tools_table)
                if existing_dim != embedding_dim:
                    logger.warning(f"tools 表维度不匹配 (现有: {existing_dim}, 需要: {embedding_dim})，重建表")
                    self.tools_table = self.db.create_table("tools", schema=self.tools_schema, mode="overwrite")
        except ImportError:
            logger.warning("LanceDB 未安装，记忆系统将使用降级模式（仅 JSON 索引）")
            self.db = None
            self.memories_table = None
            self.tools_table = None
            self.memories_schema = None
            self.tools_schema = None
    
    def _init_tool_store(self):
        """初始化工具存储"""
        self.tool_store = ToolStore(
            tools_table=self.tools_table,
            tools_schema=self.tools_schema,
            index_path=self.index_path,
            hot_threshold=self.hot_threshold,
            hot_tool_limit=self.hot_tool_limit,
            embedding_service=self.embedding_service
        )
    
    def _init_memory_store(self):
        """初始化记忆存储"""
        self.memory_store = MemoryStore(self.index_path)
    
    def _get_table_embedding_dim(self, table) -> int:
        """
        获取表中嵌入向量的维度
        
        Args:
            table: LanceDB 表对象
        
        Returns:
            嵌入向量维度
        """
        try:
            schema = table.schema
            for field in schema:
                if field.name == "embedding":
                    if hasattr(field.type, 'list_size'):
                        return field.type.list_size
                    elif hasattr(field.type, 'value_type'):
                        return field.type.value_type.list_size
            return 0
        except Exception:
            return 0
    
    def _migrate_memories_table(self, embedding_dim: int, schema):
        """
        迁移记忆表（切换嵌入模型时重新生成向量）
        
        使用批量嵌入提高迁移效率。
        
        Args:
            embedding_dim: 新的嵌入维度
            schema: 新的表 Schema
        """
        logger.info("开始迁移记忆表...")
        
        # 从MemoryStore读取所有记忆
        memories = self.memory_store.list_all()
        
        if not memories:
            logger.info("无记忆数据需要迁移，直接重建表")
            self.memories_table = self.db.create_table("memories", schema=schema, mode="overwrite")
            return
        
        logger.info(f"需要迁移 {len(memories)} 条记忆")
        
        contents = [mem["content"] for mem in memories]
        embeddings = self.embedding_service.embed_batch_sync(contents)
        
        entries = []
        for i, mem in enumerate(memories):
            embedding = embeddings[i] if i < len(embeddings) else []
            if embedding:
                entries.append({
                    "id": mem["id"],
                    "content": mem["content"],
                    "embedding": embedding,
                    "memory_type": mem.get("memory_type", "conversation"),
                    "importance": mem.get("importance", 5),
                    "tags": mem.get("tags", []),
                    "created_at": mem.get("created_at", "")
                })
        
        self.memories_table = self.db.create_table("memories", schema=schema, mode="overwrite")
        
        if self._add_memories_to_db(entries):
            logger.info(f"迁移完成: {len(entries)}/{len(memories)} 条记忆")
        else:
            logger.warning("迁移完成: 无有效记忆")
    
    def _add_memories_to_db(self, entries: List[Dict]) -> bool:
        """
        批量写入记忆到向量数据库（内部方法）
        
        Args:
            entries: 已包含 embedding 的记忆条目列表
        
        Returns:
            是否写入成功
        """
        if not entries or self.memories_table is None:
            return False
        
        try:
            self.memories_table.add(entries)
            logger.info(f"批量写入向量数据库: {len(entries)} 条记忆")
            return True
        except Exception as e:
            logger.error(f"批量写入向量数据库失败: {e}")
            return False
    
    async def _embed(self, text: str) -> List[float]:
        """获取嵌入向量"""
        return await self.embedding_service.embed(text)
    
    async def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量获取嵌入向量"""
        return await self.embedding_service.embed_batch(texts)
    
    def process_tools(self, all_tools: List[Dict]) -> Dict[str, Any]:
        """
        处理工具列表（核心方法）
        
        Args:
            all_tools: 系统加载的所有工具列表
        
        Returns:
            {"memory_tools": [...], "keep_tools": [...]}
        """
        return self.tool_store.process_tools(all_tools)
    
    async def sync_memory_tools(self, tools: List[Dict]):
        """
        异步同步工具到记忆索引
        
        Args:
            tools: 需要存入记忆索引的工具列表
        """
        await self.tool_store.sync_memory_tools(tools, self.db)
    
    async def init_async(self, all_tools: List[Dict]) -> Dict[str, Any]:
        """
        异步初始化（阻塞等待同步完成）
        
        Args:
            all_tools: 系统加载的所有工具列表
        
        Returns:
            {"keep_tools": [...], "memory_tools": [...]}
        """
        result = self.process_tools(all_tools)
        
        skill_tools = self._build_skill_tools_from_index()
        
        all_memory_tools = result["memory_tools"] + skill_tools
        
        if all_memory_tools:
            await self.sync_memory_tools(all_memory_tools)
            logger.info(f"同步 {len(all_memory_tools)} 个工具到记忆索引（内置工具: {len(result['memory_tools'])}, 技能: {len(skill_tools)}）")
        
        logger.info(f"异步初始化完成，keep_tools={len(result['keep_tools'])}, memory_tools={len(result['memory_tools'])}, skill_tools={len(skill_tools)}")
        return result
    
    def _build_skill_tools_from_index(self) -> List[Dict]:
        """
        从 tool_index.json 构建技能工具定义
        
        为 add_to_memory=true 的技能创建虚拟工具定义，
        用于向量搜索和 discover 发现。
        description 从 MD 文件的 YAML frontmatter 读取。
        
        Returns:
            技能工具定义列表
        """
        import frontmatter
        
        index_data = self.tool_store._read_tool_index()
        skill_tools = []
        
        workspace_root = self._get_workspace_root()
        
        for tool in index_data.get("tools", []):
            if tool.get("tool_type") != "skill":
                continue
            if not tool.get("add_to_memory", False):
                continue
            
            name = tool.get("name", "")
            if not name.startswith("skill_"):
                continue
            
            skill_name = name[6:]
            capability = tool.get("capability", "")
            keywords = tool.get("keywords", [])
            tags = tool.get("tags", [])
            source = tool.get("source", "")
            
            skill_md_path = ""
            description = tool.get("description", capability)
            
            if source:
                skill_md_path = os.path.join(workspace_root, source, "SKILL.md")
                try:
                    if os.path.exists(skill_md_path):
                        post = frontmatter.load(skill_md_path)
                        if "description" in post.metadata:
                            description = post.metadata["description"]
                except Exception as e:
                    logger.warning(f"读取 MD 文件失败 {skill_md_path}: {e}")
            
            keyword_str = "、".join(keywords) if keywords else ""
            tag_str = "、".join(tags) if tags else ""
            full_desc = f"{description}"
            # if keyword_str:
            #     full_desc += f"\n关键词: {keyword_str}"
            # if tag_str:
            #     full_desc += f"\n标签: {tag_str}"
            
            skill_tool = {
                "name": name,
                "description": full_desc,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": f"技能名称，固定为: {skill_name}",
                            "enum": [skill_name]
                        }
                    },
                    "required": ["skill_name"]
                },
                "tool_type": "skill",
                "skill_name": skill_name,
                "capability": capability,
                "keywords": keywords,
                "tags": tags,
                "skill_md_path": skill_md_path
            }
            skill_tools.append(skill_tool)
            logger.debug(f"构建技能工具定义: {name}, path={skill_md_path}")
        
        return skill_tools
    
    async def search_tools(self, query: str, top_k: int = 5, distance_threshold: float = 1.0) -> List[Dict]:
        """
        搜索记忆索引中的工具
        
        Args:
            query: 搜索查询
            top_k: 返回数量
            distance_threshold: L2 距离阈值
        
        Returns:
            匹配的工具列表
        """
        return await self.tool_store.search_tools(query, top_k, distance_threshold)
    
    async def search_tools_batch(
        self,
        queries: List[str],
        top_k: int = 5,
        distance_threshold: float = 1.0
    ) -> List[Dict]:
        """
        批量搜索记忆索引中的工具
        
        Args:
            queries: 搜索查询列表
            top_k: 每个查询返回数量
            distance_threshold: L2 距离阈值
        
        Returns:
            去重后的工具列表
        """
        return await self.tool_store.search_tools_batch(queries, top_k, distance_threshold)
    
    def update_tool_config(self, name: str, enabled: bool = None, add_to_memory: bool = None) -> bool:
        """
        更新工具配置
        
        Args:
            name: 工具名称
            enabled: 是否启用
            add_to_memory: 是否加入记忆索引
        
        Returns:
            是否更新成功
        """
        return self.tool_store.update_tool_config(name, enabled, add_to_memory)
    
    async def save(
        self,
        content: str,
        memory_type: str = "conversation",
        importance: int = 5,
        tags: List[str] = None,
        created_at: str = None
    ) -> str:
        """
        保存记忆
        
        Args:
            content: 记忆内容
            memory_type: 记忆类型
            importance: 重要性评分（1-10）
            tags: 标签列表
            created_at: 创建时间（可选）
        
        Returns:
            记忆 ID
        """
        memory_id = str(uuid.uuid4())[:8]
        now = created_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        date_str = now.split()[0]
        file_name = f"{date_str}.md"
        
        # 构建记忆字典
        memory = {
            "id": memory_id,
            "content": content,
            "memory_type": memory_type,
            "importance": importance,
            "tags": tags or [],
            "created_at": now
        }
        
        # 获取写入锁（防止 watchdog 重复处理）
        self.memory_store.acquire_write_lock(file_name)
        
        try:
            # 保存到MD文件
            self.memory_store.save(memory)
            
            # 保存到向量数据库
            if self.memories_table is not None:
                embedding = await self._embed(content)
                if embedding:
                    entry = {
                        "id": memory_id,
                        "content": content,
                        "embedding": embedding,
                        "memory_type": memory_type,
                        "importance": importance,
                        "tags": tags or [],
                        "created_at": now
                    }
                    try:
                        self.memories_table.add([entry])
                    except Exception as e:
                        logger.error(f"向量数据库写入失败: {e}")
            
            logger.info(f"记忆已保存: {memory_id}")
            return memory_id
        finally:
            # 延迟释放锁，确保 watchdog 能检测到锁状态
            await asyncio.sleep(0.3)
            self.memory_store.release_write_lock(file_name)
    
    async def save_batch(self, items: List[Dict[str, Any]]) -> List[str]:
        """
        批量保存记忆（高性能版本）
        
        Args:
            items: 记忆条目列表
        
        Returns:
            记忆 ID 列表
        """
        if not items:
            return []
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 构建记忆列表
        memories = []
        memory_ids = []
        for item in items:
            memory_id = str(uuid.uuid4())[:8]
            memory_ids.append(memory_id)
            memory = {
                "id": memory_id,
                "content": item.get("content", ""),
                "memory_type": item.get("memory_type", "conversation"),
                "importance": item.get("importance", 5),
                "tags": item.get("tags", []),
                "created_at": item.get("created_at", now)
            }
            memories.append(memory)
        
        # 保存到MD文件
        self.memory_store.save_batch(memories)
        
        # 保存到向量数据库
        if self.memories_table is not None:
            contents = [item.get("content", "") for item in items]
            embeddings = await self._embed_batch(contents)
            
            entries = []
            for i, memory in enumerate(memories):
                embedding = embeddings[i] if i < len(embeddings) else []
                if embedding:
                    entries.append({
                        "id": memory["id"],
                        "content": memory["content"],
                        "embedding": embedding,
                        "memory_type": memory["memory_type"],
                        "importance": memory["importance"],
                        "tags": memory["tags"],
                        "created_at": memory["created_at"]
                    })
            
            self._add_memories_to_db(entries)
        
        logger.info(f"批量保存记忆完成: {len(memory_ids)} 条")
        return memory_ids
    
    async def search(
        self,
        query: str,
        search_type: str = "all",
        top_k: int = 10,
        tags: List[str] = None,
        category: str = None,
        distance_threshold: float = 1.0,
        date_range: Tuple[str, str] = None
    ) -> Dict[str, List[Dict]]:
        """
        统一搜索
        
        Args:
            query: 搜索查询
            search_type: 搜索范围（all/memory/tool）
            top_k: 返回数量
            tags: 标签过滤（仅工具）
            category: 分类过滤（仅工具）
            distance_threshold: L2 距离阈值
            date_range: 日期范围过滤（记忆），格式：(start_date, end_date)，如 ("2026-03-01", "2026-03-06")
        
        Returns:
            {"memories": [...], "tools": [...]}
        """
        # 同步MD文件变更到向量库
        if search_type in ["all", "memory"]:
            changes = self.memory_store.sync_to_vector_db(self.memories_table)
            await self._sync_changes_to_vector_db(changes)
        
        query_embedding = await self._embed(query)
        results = {"memories": [], "tools": []}
        
        if not query_embedding:
            return results
        
        if search_type in ["all", "memory"] and self.memories_table is not None:
            try:
                # 构建查询
                search_query = self.memories_table.search(query_embedding)
                
                # 添加日期范围过滤
                # 注意：created_at 格式为 "2026-03-12 18:19:27"，需要将 date_range 扩展为完整时间格式
                if date_range:
                    start_date, end_date = date_range
                    # 开始日期从 00:00:00，结束日期到 23:59:59
                    start_datetime = f"{start_date} 00:00:00"
                    end_datetime = f"{end_date} 23:59:59"
                    where_clause = f"created_at >= '{start_datetime}' AND created_at <= '{end_datetime}'"
                    search_query = search_query.where(where_clause)
                
                rows = search_query.limit(top_k * 2).to_list()
                
                for r in rows:
                    distance = r.get("_distance", 999.0)
                    if distance > distance_threshold:
                        continue
                    results["memories"].append({
                        "id": r["id"],
                        "content": r["content"],
                        "type": r.get("memory_type", "conversation"),
                        "importance": r.get("importance", 5),
                        "tags": r.get("tags", []),
                        "created_at": r.get("created_at", "")
                    })
                    if len(results["memories"]) >= top_k:
                        break
            except Exception:
                pass
        
        if search_type in ["all", "tool"] and self.tools_table is not None:
            try:
                rows = self.tools_table.search(query_embedding).limit(top_k * 2).to_list()
                for r in rows:
                    distance = r.get("_distance", 999.0)
                    tool_name = r.get("name", "unknown")
                    logger.debug(f"[搜索] 工具: {tool_name}, distance={distance:.4f}, threshold={distance_threshold}")
                    if distance > distance_threshold:
                        continue
                    
                    tool_tags = r.get("tags", [])
                    tool_category = r.get("category", "")
                    
                    if tags and not any(t in tool_tags for t in tags):
                        continue
                    if category and tool_category != category:
                        continue
                    
                    tool_def = json5.loads(r.get("tool_definition", "{}"))
                    results["tools"].append(tool_def)
                    self.tool_store._increment_query_count(r["name"])
                    
                    if len(results["tools"]) >= top_k:
                        break
            except Exception:
                pass
        
        return results
    
    async def delete(self, memory_id: str) -> bool:
        """
        删除记忆
        
        Args:
            memory_id: 记忆 ID
        
        Returns:
            是否删除成功
        """
        try:
            # 先获取原记忆以确定文件名
            old_memory = self.memory_store.get(memory_id)
            if old_memory:
                date_str = old_memory.get("created_at", "").split()[0]
            else:
                date_str = datetime.now().strftime("%Y-%m-%d")
            file_name = f"{date_str}.md"
            
            # 获取写入锁（防止 watchdog 重复处理）
            self.memory_store.acquire_write_lock(file_name)
            
            try:
                # 从MD文件删除
                self.memory_store.delete(memory_id)
                
                # 从向量数据库删除
                if self.memories_table is not None:
                    self.memories_table.delete(f"id = '{memory_id}'")
                
                return True
            finally:
                # 延迟释放锁
                await asyncio.sleep(0.3)
                self.memory_store.release_write_lock(file_name)
                
        except Exception as e:
            logger.error(f"删除记忆失败: {e}")
            return False
    
    async def update(self, memory_id: str, **kwargs) -> Optional[Dict]:
        """
        更新记忆
        
        更新MD文件中的记忆内容，并同步更新向量数据库
        
        Args:
            memory_id: 记忆ID
            **kwargs: 要更新的字段，可包含:
                - content: 记忆内容
                - memory_type: 记忆类型
                - importance: 重要性评分
                - tags: 标签列表
        
        Returns:
            更新后的记忆字典，未找到返回None
        """
        try:
            # 过滤有效字段
            valid_fields = {"content", "memory_type", "importance", "tags"}
            updates = {k: v for k, v in kwargs.items() if k in valid_fields}
            
            if not updates:
                logger.warning(f"更新记忆 {memory_id}: 没有提供有效字段")
                return None
            
            # 先获取原记忆以确定文件名
            old_memory = self.memory_store.get(memory_id)
            if old_memory:
                date_str = old_memory.get("created_at", "").split()[0]
            else:
                date_str = datetime.now().strftime("%Y-%m-%d")
            file_name = f"{date_str}.md"
            
            # 获取写入锁（防止 watchdog 重复处理）
            self.memory_store.acquire_write_lock(file_name)
            
            try:
                # 更新MD文件
                updated_memory = self.memory_store.update(memory_id, updates)
                
                if not updated_memory:
                    return None
                
                # 更新向量数据库
                if self.memories_table is not None:
                    # 删除旧记录
                    self.memories_table.delete(f"id = '{memory_id}'")
                    
                    # 重新计算embedding并插入新记录
                    embedding = await self._embed(updated_memory["content"])
                    if embedding:
                        entry = {
                            "id": updated_memory["id"],
                            "content": updated_memory["content"],
                            "embedding": embedding,
                            "memory_type": updated_memory["memory_type"],
                            "importance": updated_memory["importance"],
                            "tags": updated_memory["tags"],
                            "created_at": updated_memory["created_at"]
                        }
                        self.memories_table.add([entry])
                        logger.info(f"向量数据库已更新: {memory_id}")
                
                logger.info(f"记忆更新完成: {memory_id}")
                return updated_memory
            finally:
                # 延迟释放锁
                await asyncio.sleep(0.3)
                self.memory_store.release_write_lock(file_name)
            
        except Exception as e:
            logger.error(f"更新记忆失败 {memory_id}: {e}")
            return None
    
    async def list_memories(
        self,
        top_k: int = 10,
        full: bool = True,
        order: str = "desc",
        max_content_length: int = 200
    ) -> Dict[str, Any]:
        """
        列出记忆（不需要搜索关键词）
        
        Args:
            top_k: 返回数量
            full: 是否返回完整内容
            order: 排序方式
            max_content_length: 内容截断长度
        
        Returns:
            {"total_count": N, "returned_count": M, "memories": [...]}
        """
        try:
            # 同步MD文件变更到向量库
            changes = self.memory_store.sync_to_vector_db(self.memories_table)
            
            # 处理新增和修改的记录（需要重新计算embedding）
            await self._sync_changes_to_vector_db(changes)
            
            # 从MD文件读取所有记忆
            all_memories = self.memory_store.list_all()
            total_count = len(all_memories)
            
            # 排序
            reverse_order = (order == "desc")
            sorted_memories = sorted(
                all_memories,
                key=lambda x: x.get("created_at", ""),
                reverse=reverse_order
            )
            
            # 限制数量
            limited_memories = sorted_memories[:top_k]
            
            # 格式化输出
            memories = []
            for m in limited_memories:
                content = m.get("content", "")
                if not full and len(content) > max_content_length:
                    content = content[:max_content_length] + "..."
                
                memories.append({
                    "id": m.get("id", ""),
                    "content": content,
                    "type": m.get("memory_type", "conversation"),
                    "importance": int(m.get("importance", 5)),
                    "tags": m.get("tags", []),
                    "created_at": m.get("created_at", "")
                })
            
            return {
                "total_count": total_count,
                "returned_count": len(memories),
                "memories": memories
            }
        except Exception as e:
            logger.error(f"列出记忆失败: {e}")
            return {"total_count": 0, "returned_count": 0, "memories": []}
    
    async def _sync_changes_to_vector_db(self, changes: Dict[str, List]):
        """
        将变更同步到向量数据库
        
        Args:
            changes: 变更记录 {"added": [], "deleted": [], "modified": []}
        """
        if self.memories_table is None:
            return
        
        try:
            # 处理新增的记录
            if changes["added"]:
                contents = [m["content"] for m in changes["added"]]
                embeddings = await self._embed_batch(contents)
                
                entries = []
                for i, memory in enumerate(changes["added"]):
                    if i < len(embeddings) and embeddings[i]:
                        entries.append({
                            "id": memory["id"],
                            "content": memory["content"],
                            "embedding": embeddings[i],
                            "memory_type": memory.get("memory_type", "conversation"),
                            "importance": memory.get("importance", 5),
                            "tags": memory.get("tags", []),
                            "created_at": memory.get("created_at", "")
                        })
                
                if entries:
                    self.memories_table.add(entries)
                    logger.info(f"同步新增记录到向量库: {len(entries)} 条")
            
            # 处理修改的记录（先删后插）
            if changes["modified"]:
                contents = [m["content"] for m in changes["modified"]]
                embeddings = await self._embed_batch(contents)
                
                entries = []
                for i, memory in enumerate(changes["modified"]):
                    # 删除旧记录
                    self.memories_table.delete(f"id = '{memory['id']}'")
                    # 准备新记录
                    if i < len(embeddings) and embeddings[i]:
                        entries.append({
                            "id": memory["id"],
                            "content": memory["content"],
                            "embedding": embeddings[i],
                            "memory_type": memory.get("memory_type", "conversation"),
                            "importance": memory.get("importance", 5),
                            "tags": memory.get("tags", []),
                            "created_at": memory.get("created_at", "")
                        })
                
                if entries:
                    self.memories_table.add(entries)
                    logger.info(f"同步修改记录到向量库: {len(entries)} 条")
        
        except Exception as e:
            logger.error(f"同步变更到向量库失败: {e}")
    
    async def register_tool(
        self,
        name: str,
        description: str,
        tool_type: str = "skill",
        source: str = "",
        enabled: bool = True,
        add_to_memory: bool = True
    ) -> str:
        """
        注册工具到索引
        
        Args:
            name: 工具名称
            description: 工具描述
            tool_type: 工具类型
            source: 工具来源路径
            enabled: 是否启用
            add_to_memory: 是否加入记忆索引
        
        Returns:
            工具名称
        """
        return await self.tool_store.register_tool(name, description, tool_type, source, enabled, add_to_memory)
    
    async def unregister_tool(self, name: str) -> bool:
        """
        从索引移除工具
        
        Args:
            name: 工具名称
        
        Returns:
            是否移除成功
        """
        return await self.tool_store.unregister_tool(name)
    
    def get_memory_tools(self) -> List[Dict]:
        """
        获取需要存入记忆索引的工具列表
        
        Returns:
            工具列表
        """
        return self.tool_store.get_memory_tools()
    
    def compact(self, table_name: str = "all") -> bool:
        """
        压缩数据库表，减少碎片
        
        Args:
            table_name: 要压缩的表名
        
        Returns:
            是否压缩成功
        """
        if self.db is None:
            logger.warning("数据库未初始化，无法压缩")
            return False
        
        try:
            tables_to_compact = []
            if table_name in ["all", "memories"] and self.memories_table is not None:
                tables_to_compact.append(("memories", self.memories_table))
            if table_name in ["all", "tools"] and self.tools_table is not None:
                tables_to_compact.append(("tools", self.tools_table))
            
            for name, table in tables_to_compact:
                if hasattr(table, 'compact_files'):
                    table.compact_files()
                    logger.info(f"表 {name} 压缩完成")
                else:
                    logger.info(f"表 {name} 不支持压缩（需要安装 pylance）")
            
            return True
        except Exception as e:
            logger.error(f"压缩数据库失败: {e}")
            return False
    
    def is_enabled(self) -> bool:
        """检查记忆系统是否启用"""
        return self.config.get("enabled", True)
    
    def get_all_capabilities(self) -> List[str]:
        """
        获取所有能力标签（用于任务拆解阶段）

        Returns:
            能力标签列表
        """
        return self.tool_store.get_all_capabilities()

    def start_file_watcher(
        self,
        config_path: Optional[str] = None,
        reload_config_callback: Optional[Any] = None
    ) -> Optional[Any]:
        """
        启动文件监控器

        监控 MD 记忆文件变更和配置文件热加载。
        根据 config.file_watcher.enabled 配置决定是否启动。

        Args:
            config_path: 配置文件目录路径
            reload_config_callback: 配置文件变更时的回调函数

        Returns:
            FileWatcher 实例，如果未启用或启动失败返回 None
        """
        from agent.watchdog.file_watcher_start import start_file_watcher

        return start_file_watcher(
            memory_system=self,
            config_path=config_path,
            reload_config_callback=reload_config_callback
        )

    def stop_file_watcher(self) -> bool:
        """
        停止文件监控器

        Returns:
            是否成功停止
        """
        from agent.watchdog.file_watcher_start import stop_file_watcher

        return stop_file_watcher()

    def is_file_watcher_running(self) -> bool:
        """
        检查文件监控器是否正在运行

        Returns:
            是否正在运行
        """
        from agent.watchdog.file_watcher_start import is_file_watcher_running

        return is_file_watcher_running()
