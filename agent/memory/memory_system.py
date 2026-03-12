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

import threading
from typing import List, Dict, Any
from pathlib import Path
from datetime import datetime
import json
import json5
import uuid
import asyncio
import os

from loguru import logger


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
        embedding: 嵌入服务配置
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
        self.embedding = self._init_embedding(config.get("embedding", {}), workspace_root)
        self._init_db()
        # 开启子线程thread 初始化嵌入模型和数据库
        # thread = threading.Thread(target=self.thread_safe_embed, args=(self.config, workspace_root))
        # thread.start()
        # thread.join()
        
        
        
        logger.info(f"记忆系统初始化完成: db={self.db_path}, index={self.index_path}")
    
    def thread_safe_embed(self, config: Dict[str, Any], workspace_root: str):
        """
        子线程中调用_init_embedding和 self._init_db()
        Args:
            config: 嵌入服务配置
            workspace_root: 工作空间根目录
        
        Returns:
            嵌入向量列表
        """
        self.embedding = self._init_embedding(config.get("embedding", {}), workspace_root)
        self._init_db()
    
    
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
        
        if not memory_index_file.exists():
            memory_index_content = '''{
    // ==========================================
    // 记忆索引文件 - 存储用户的长期记忆
    // ==========================================
    // 
    // 字段说明：
    //   id: 记忆唯一标识（8位UUID）
    //   content: 记忆内容
    //   memory_type: 记忆类型
    //     - conversation: 对话记录
    //     - fact: 事实信息
    //     - preference: 用户偏好
    //     - task: 任务结果
    //     - insight: 洞察总结
    //     - document: 文档摘要
    //   importance: 重要性评分（1-10，默认5）
    //   tags: 标签列表（用于分类和检索）
    //   created_at: 创建时间
    //
    // ==========================================
    
    "version": "1.0",
    "updated_at": "''' + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + '''",
    "memories": [
        // 示例：用户偏好
        // {
        //     "id": "pref001",
        //     "content": "用户偏好使用中文交流，工作语言为Python",
        //     "memory_type": "preference",
        //     "importance": 8,
        //     "tags": ["language", "programming"],
        //     "created_at": "2026-03-05 10:00:00"
        // },
        // 
        // 示例：事实信息
        // {
        //     "id": "fact001",
        //     "content": "项目使用FastAPI框架，数据库为PostgreSQL",
        //     "memory_type": "fact",
        //     "importance": 7,
        //     "tags": ["project", "tech_stack"],
        //     "created_at": "2026-03-05 10:30:00"
        // },
        // 
        // 示例：任务结果
        // {
        //     "id": "task001",
        //     "content": "已完成用户认证模块的开发，使用JWT令牌",
        //     "memory_type": "task",
        //     "importance": 6,
        //     "tags": ["completed", "auth"],
        //     "created_at": "2026-03-05 14:00:00"
        // }
    ]
}'''
            with open(memory_index_file, "w", encoding="utf-8") as f:
                f.write(memory_index_content)
            logger.info(f"创建记忆索引文件: {memory_index_file}")
    
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
    
    def _init_db(self):
        """初始化数据库连接和表"""
        db_path = Path(self.db_path)
        db_path.mkdir(parents=True, exist_ok=True)
        
        try:
            import lancedb
            import pyarrow as pa
            
            embedding_dim = self._get_embedding_dim()
            
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
    
    def _migrate_memories_table(self, embedding_dim: int, schema):
        """
        迁移记忆表（切换嵌入模型时重新生成向量）
        
        使用批量嵌入提高迁移效率。
        
        Args:
            embedding_dim: 新的嵌入维度
            schema: 新的表 Schema
        """
        logger.info("开始迁移记忆表...")
        
        memory_index = self._read_memory_index()
        memories = memory_index.get("memories", [])
        
        if not memories:
            logger.info("无记忆数据需要迁移，直接重建表")
            self.memories_table = self.db.create_table("memories", schema=schema, mode="overwrite")
            return
        
        logger.info(f"需要迁移 {len(memories)} 条记忆")
        
        contents = [mem["content"] for mem in memories]
        embeddings = self._embed_batch_sync(contents)
        
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
    
    def _embed_batch_sync(self, texts: List[str]) -> List[List[float]]:
        """
        批量同步获取嵌入向量（用于迁移等场景）
        
        Args:
            texts: 输入文本列表
        
        Returns:
            归一化的嵌入向量列表的列表
        """
        import numpy as np
        from concurrent.futures import ThreadPoolExecutor
        
        if self.embedding["type"] == "local":
            embeddings = self.embedding["model"].encode(texts)
        elif self.embedding["type"] == "gguf":
            model = self.embedding["model"]
            batch_size = self.embedding.get("batch_size", 8)
            embeddings = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                result = model.create_embedding(batch)
                embeddings.extend([item["embedding"] for item in result["data"]])
        elif self.embedding["type"] == "api":
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            
            if loop and loop.is_running():
                with ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self._embed_batch(texts)
                    )
                    return future.result()
            else:
                return asyncio.run(self._embed_batch(texts))
        else:
            return [[] for _ in texts]
        
        results = []
        for emb in embeddings:
            vec = np.array(emb)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            results.append(vec.tolist())
        
        return results
    
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
    
    def _get_embedding_dim(self) -> int:
        """获取嵌入向量维度"""
        if self.embedding["type"] == "none":
            return 384
        
        try:
            if self.embedding["type"] == "local":
                sample_embedding = self.embedding["model"].encode("test").tolist()
                return len(sample_embedding) if sample_embedding else 384
            elif self.embedding["type"] == "gguf":
                sample_embedding = self.embedding["model"].embed("test")
                return len(sample_embedding) if sample_embedding else 384
            elif self.embedding["type"] == "api":
                import asyncio
                sample_embedding = asyncio.run(self._embed("test"))
                return len(sample_embedding) if sample_embedding else 384
            return 384
        except Exception as e:
            logger.warning(f"获取嵌入维度失败: {e}")
            return 384
    
    def _init_embedding(self, config: Dict, workspace_root: str) -> Dict:
        """
        初始化嵌入服务
        
        根据 local_model 扩展名自动判断格式：
        - .gguf 结尾：使用 llama-cpp-python 加载
        - 其他：使用 sentence-transformers 加载（HuggingFace 格式）
        
        Args:
            config: 嵌入服务配置
            workspace_root: 工作区根目录
        
        Returns:
            嵌入服务配置字典
        """
        provider = config.get("provider", "local")
        
        if provider == "local":
            local_model = config.get("local_model", "BAAI/bge-small-zh-v1.5")
            
            if local_model.endswith(".gguf"):
                return self._init_gguf_embedding(local_model, workspace_root)
            else:
                return self._init_huggingface_embedding(local_model, config, workspace_root)
        
        return self._init_api_embedding(config)
    
    def _init_gguf_embedding(self, model_path: str, workspace_root: str) -> Dict:
        """初始化 GGUF 格式嵌入模型"""
        try:
            from llama_cpp import Llama
            
            model_path = self._resolve_path(model_path, workspace_root)
            
            if not os.path.exists(model_path):
                logger.warning(f"GGUF 模型文件不存在: {model_path}")
                return {"type": "none"}
            
            logger.info(f"加载 GGUF 嵌入模型: {model_path}")
            
            llm = Llama(
                model_path=model_path,
                embedding=True,
                n_ctx=8192,
                n_batch=2048,
                n_ubatch=2048,
                n_gpu_layers=-1,
                n_threads=8,
                verbose=False
            )
            
            return {"type": "gguf", "model": llm, "batch_size": 1}
        except ImportError:
            logger.warning("llama-cpp-python 未安装，GGUF 嵌入功能将不可用。安装: pip install llama-cpp-python")
            return {"type": "none"}
        except Exception as e:
            logger.warning(f"加载 GGUF 模型失败: {e}")
            return {"type": "none"}
    
    def _init_huggingface_embedding(self, model_name: str, config: Dict, workspace_root: str) -> Dict:
        """初始化 HuggingFace 格式嵌入模型"""
        try:
            from sentence_transformers import SentenceTransformer
            
            cache_folder = config.get("cache_folder")
            
            if cache_folder:
                cache_folder = self._resolve_path(cache_folder, workspace_root)
                logger.info(f"加载 HuggingFace 嵌入模型: {model_name}, 缓存目录: {cache_folder}")
                model = SentenceTransformer(model_name, cache_folder=cache_folder)
            else:
                logger.info(f"加载 HuggingFace 嵌入模型: {model_name}")
                model = SentenceTransformer(model_name)
            
            return {"type": "local", "model": model}
        except ImportError:
            logger.warning("sentence-transformers 未安装，嵌入功能将不可用")
            return {"type": "none"}
    
    def _init_api_embedding(self, config: Dict) -> Dict:
        """初始化 API 嵌入服务"""
        try:
            from openai import AsyncOpenAI
            
            provider = config.get("provider", "openai")
            base_urls = {
                "openai": None,
                "zhipu": "https://open.bigmodel.cn/api/paas/v4/",
                "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "deepseek": "https://api.deepseek.com/v1",
                "custom": config.get("base_url")
            }
            return {
                "type": "api",
                "client": AsyncOpenAI(
                    api_key=config.get("api_key", ""),
                    base_url=base_urls.get(provider)
                ),
                "model": config.get("model", "text-embedding-3-small")
            }
        except ImportError:
            logger.warning("openai 未安装，API 嵌入功能将不可用")
            return {"type": "none"}
    
    async def _embed(self, text: str) -> List[float]:
        """
        获取嵌入向量（归一化）
        
        Args:
            text: 输入文本
        
        Returns:
            归一化的嵌入向量列表
        """
        if self.embedding["type"] == "local":
            embedding = self.embedding["model"].encode(text)
        elif self.embedding["type"] == "gguf":
            embedding = self.embedding["model"].embed(text)
        elif self.embedding["type"] == "api":
            resp = await self.embedding["client"].embeddings.create(
                input=text, 
                model=self.embedding["model"]
            )
            embedding = resp.data[0].embedding
        else:
            return []
        
        import numpy as np
        vec = np.array(embedding)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()
    
    async def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量获取嵌入向量（归一化）
        
        Args:
            texts: 输入文本列表
        
        Returns:
            归一化的嵌入向量列表的列表
        """
        import numpy as np
        
        if self.embedding["type"] == "local":
            embeddings = self.embedding["model"].encode(texts)
        elif self.embedding["type"] == "gguf":
            model = self.embedding["model"]
            batch_size = self.embedding.get("batch_size", 8)
            embeddings = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                result = model.create_embedding(batch)
                embeddings.extend([item["embedding"] for item in result["data"]])
        elif self.embedding["type"] == "api":
            embeddings = await asyncio.gather(*[self._embed(t) for t in texts])
            return embeddings
        else:
            return [[] for _ in texts]
        
        results = []
        for emb in embeddings:
            vec = np.array(emb)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            results.append(vec.tolist())
        
        return results
    
    def _read_tool_index(self) -> Dict:
        """读取工具索引 JSON 文件（支持 JSON5 格式）"""
        index_file = self.index_path / "tool_index.json"
        if not index_file.exists():
            return {"version": "1.0", "updated_at": "", "tools": []}
        
        with open(index_file, "r", encoding="utf-8") as f:
            return json5.load(f)
    
    def _write_tool_index(self, data: Dict):
        """写入工具索引 JSON 文件（标准 JSON 格式）"""
        data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        index_file = self.index_path / "tool_index.json"
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _read_memory_index(self) -> Dict:
        """读取记忆索引 JSON 文件（支持 JSON5 格式）"""
        index_file = self.index_path / "memory_index.json"
        if not index_file.exists():
            return {"version": "1.0", "updated_at": "", "memories": []}
        
        with open(index_file, "r", encoding="utf-8") as f:
            return json5.load(f)
    
    def _write_memory_index(self, data: Dict):
        """写入记忆索引 JSON 文件（标准 JSON 格式）"""
        data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        index_file = self.index_path / "memory_index.json"
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def process_tools(self, all_tools: List[Dict]) -> Dict[str, Any]:
        """
        处理工具列表（核心方法）
        
        根据索引文件配置处理工具：
        - enabled=false → 从工具列表移除
        - enabled=true, add_to_memory=false → 保留在工具列表
        - enabled=true, add_to_memory=true → 存入记忆索引并移除
        
        匹配规则：
        - name 必须与系统工具名完全一致
        - skill 类型使用完整名（如 "skill_xxx"）
        - builtin 类型使用原始名称（如 "file_read"）
        
        Args:
            all_tools: 系统加载的所有工具列表
        
        Returns:
            {
                "memory_tools": List[Dict],  # 存入记忆索引的工具
                "keep_tools": List[Dict]     # 保留在工具列表的工具
            }
        """
        index_data = self._read_tool_index()
        index_map = {t["name"]: t for t in index_data.get("tools", [])}
        
        memory_tools = []
        keep_tools = []
        disabled_tools = []
        
        for tool in all_tools:
            func_def = tool.get("function", tool)
            tool_name = func_def.get("name")
            
            if not tool_name:
                logger.warning(f"  - 工具缺少名称，跳过: {tool}")
                continue
            
            index_entry = index_map.get(tool_name)
            
            if index_entry:
                enabled = index_entry.get("enabled", True)
                add_to_memory = index_entry.get("add_to_memory", True)
                
                if not enabled:
                    disabled_tools.append(tool_name)
                    logger.debug(f"  - 工具已禁用: {tool_name}")
                    continue
                
                if add_to_memory:
                    memory_tools.append(tool)
                    logger.debug(f"  - 工具加入记忆索引: {tool_name}")
                else:
                    keep_tools.append(tool)
                    logger.debug(f"  - 工具保留常驻: {tool_name}")
            else:
                keep_tools.append(tool)
                logger.debug(f"  - 工具未在索引中，保留常驻: {tool_name}")
        
        if disabled_tools:
            logger.info(f"工具分类完成: 禁用={len(disabled_tools)}, 记忆索引={len(memory_tools)}, 常驻={len(keep_tools)}")
        
        return {"memory_tools": memory_tools, "keep_tools": keep_tools}
    
    async def sync_memory_tools(self, tools: List[Dict]):
        """
        异步同步工具到记忆索引
        
        直接存储完整的 Function Call 定义，不做映射
        使用全量同步（重建表），避免碎片产生
        
        Args:
            tools: 需要存入记忆索引的工具列表
        """
        if not tools or self.tools_schema is None:
            return
        
        index_data = self._read_tool_index()
        index_map = {t["name"]: t for t in index_data.get("tools", [])}
        
        texts = []
        for t in tools:
            func_def = t.get("function", t)
            name = func_def.get("name", "unknown")
            desc = func_def.get("description", "")
            
            index_entry = index_map.get(name, {})
            keywords = " ".join(index_entry.get("keywords", []))
            tags = " ".join(index_entry.get("tags", []))
            
            text_parts = [f"{name}: {desc}"]
            if keywords:
                text_parts.append(keywords)
            if tags:
                text_parts.append(tags)
            
            texts.append(" ".join(text_parts))
        
        embeddings = await self._embed_batch(texts)
        
        entries = []
        for tool, emb in zip(tools, embeddings):
            func_def = tool.get("function", tool)
            name = func_def.get("name", "unknown")
            tool_type = tool.get("tool_type", "skill")
            tool_id = f"{tool_type}:{name}"
            entries.append({
                "id": tool_id,
                "name": name,
                "tool_type": tool_type,
                "embedding": emb,
                "tool_definition": json5.dumps(tool, ensure_ascii=False),
                "query_count": 0
            })
            logger.debug(f"  - 初始化工具到记忆索引: {name} (type={tool_type})")
        
        self.tools_table = self.db.create_table("tools", schema=self.tools_schema, mode="overwrite")
        if entries:
            self.tools_table.add(entries)
        logger.info(f"记忆索引同步完成，共 {len(entries)} 个工具")
    
    async def init_async(self, all_tools: List[Dict]) -> Dict[str, Any]:
        """
        异步初始化（阻塞等待同步完成）
        
        Args:
            all_tools: 系统加载的所有工具列表
        
        Returns:
            {"keep_tools": [...], "memory_tools": [...]}
        """
        result = self.process_tools(all_tools)
        
        await self.sync_memory_tools(result["memory_tools"])
        
        logger.info(f"异步初始化完成，keep_tools={len(result['keep_tools'])}, memory_tools={len(result['memory_tools'])}")
        return result
    
    async def search_tools(self, query: str, top_k: int = 5, distance_threshold: float = 1.0) -> List[Dict]:
        """
        搜索记忆索引中的工具
        
        Args:
            query: 搜索查询
            top_k: 返回数量
            distance_threshold: L2 距离阈值，距离越小越相似，默认 1.0
        
        Returns:
            匹配的工具列表（完整的 Function Call 定义）
        """
        logger.info(f"[工具搜索] 开始搜索, query={query[:50]}..., top_k={top_k}, threshold={distance_threshold}")
        
        if self.tools_table is None:
            logger.warning("[工具搜索] tools_table 为 None，跳过搜索")
            return []
        
        query_embedding = await self._embed(query)
        if not query_embedding:
            logger.warning("[工具搜索] query_embedding 为空，跳过搜索")
            return []
        
        try:
            rows = self.tools_table.search(query_embedding).limit(top_k * 2).to_list()
            logger.info(f"[工具搜索] 查询返回 {len(rows)} 条结果")
            
            results = []
            for r in rows:
                distance = r.get("_distance", 999.0)
                logger.info(f"[工具搜索] 工具: {r['name']}, distance={distance:.4f}")
                
                if distance > distance_threshold:
                    logger.info(f"[工具搜索] 工具 {r['name']} 距离 {distance:.4f} 超过阈值 {distance_threshold}，跳过")
                    continue
                
                tool_def = json5.loads(r.get("tool_definition", "{}"))
                results.append(tool_def)
                self._increment_query_count(r["name"])
                
                if len(results) >= top_k:
                    break
            
            logger.info(f"[工具搜索] 完成，返回 {len(results)} 个工具")
            return results
        except Exception as e:
            logger.error(f"搜索工具失败: {e}")
            return []
    
    async def search_tools_batch(
        self, 
        queries: List[str], 
        top_k: int = 5, 
        distance_threshold: float = 1.0
    ) -> List[Dict]:
        """
        批量搜索记忆索引中的工具
        
        使用 lancedb 的批量查询功能，一次处理多个查询，提高效率。
        结果自动去重（基于工具名称）。
        
        Args:
            queries: 搜索查询列表
            top_k: 每个查询返回数量
            distance_threshold: L2 距离阈值，距离越小越相似，默认 1.0
        
        Returns:
            去重后的工具列表（完整的 Function Call 定义）
        """
        if not queries:
            return []
        
        if len(queries) == 1:
            return await self.search_tools(queries[0], top_k, distance_threshold)
        
        logger.info(f"[批量工具搜索] 开始批量搜索, queries={len(queries)}, top_k={top_k}, threshold={distance_threshold}")
        
        if self.tools_table is None:
            logger.warning("[批量工具搜索] tools_table 为 None，跳过搜索")
            return []
        
        query_embeddings = await self._embed_batch(queries)
        if not any(query_embeddings):
            logger.warning("[批量工具搜索] query_embeddings 为空，跳过搜索")
            return []
        
        try:
            valid_embeddings = [emb for emb in query_embeddings if emb]
            if not valid_embeddings:
                return []
            
            rows = self.tools_table.search(valid_embeddings).limit(top_k * 2).to_list()
            logger.info(f"[批量工具搜索] 查询返回 {len(rows)} 条结果")
            
            seen_names = set()
            results = []
            query_count_incremented = set()
            
            for r in rows:
                distance = r.get("_distance", 999.0)
                tool_name = r.get("name", "")
                
                if distance > distance_threshold:
                    logger.debug(f"[批量工具搜索] 工具 {tool_name} 距离 {distance:.4f} 超过阈值 {distance_threshold}，跳过")
                    continue
                
                if tool_name in seen_names:
                    continue
                
                seen_names.add(tool_name)
                tool_def = json5.loads(r.get("tool_definition", "{}"))
                results.append(tool_def)
                
                if tool_name not in query_count_incremented:
                    self._increment_query_count(tool_name)
                    query_count_incremented.add(tool_name)
            
            logger.info(f"[批量工具搜索] 完成，返回 {len(results)} 个去重工具")
            return results
        except Exception as e:
            logger.error(f"批量搜索工具失败: {e}")
            return []
    
    def _increment_query_count(self, tool_name: str):
        """
        增加工具查询次数
        
        当工具查询次数达到 hot_threshold 时，进入候选池。
        从候选池中取前 hot_tool_limit 个转为常驻加载。
        
        匹配规则：name 必须与系统工具名完全一致
        """
        data = self._read_tool_index()
        for tool in data.get("tools", []):
            if tool["name"] == tool_name:
                tool["query_count"] = tool.get("query_count", 0) + 1
                self._write_tool_index(data)
                self._update_hot_tools()
                return
    
    def _update_hot_tools(self):
        """
        更新热点工具状态
        
        逻辑：
        1. 获取所有达到 hot_threshold 的工具（排除核心工具）
        2. 按查询次数降序排序
        3. 取前 hot_tool_limit 个转为常驻（add_to_memory=False）
        
        注意：核心工具（category=core）不参与热点调整，保持用户配置
        """
        data = self._read_tool_index()
        tools = data.get("tools", [])
        
        core_tool_names = {t["name"] for t in tools if t.get("category") == "core"}
        
        hot_candidates = [
            t for t in tools
            if t.get("query_count", 0) >= self.hot_threshold
            and t.get("category") != "core"
        ]
        
        hot_candidates.sort(key=lambda x: x.get("query_count", 0), reverse=True)
        
        hot_tool_names = {t["name"] for t in hot_candidates[:self.hot_tool_limit]}
        
        changed = False
        for tool in tools:
            if tool["name"] in core_tool_names:
                continue
            
            if tool["name"] in hot_tool_names:
                if tool.get("add_to_memory", True):
                    tool["add_to_memory"] = False
                    changed = True
                    logger.info(f"热点工具转为常驻: {tool['name']} (query_count={tool.get('query_count', 0)})")
            else:
                if not tool.get("add_to_memory", True) and tool.get("query_count", 0) < self.hot_threshold:
                    tool["add_to_memory"] = True
                    changed = True
        
        if changed:
            self._write_tool_index(data)
    
    def update_tool_config(self, name: str, enabled: bool = None, add_to_memory: bool = None) -> bool:
        """
        更新工具配置
        
        Args:
            name: 工具名称（必须与系统工具名完全一致）
            enabled: 是否启用
            add_to_memory: 是否加入记忆索引
        
        Returns:
            是否更新成功
        """
        data = self._read_tool_index()
        
        for tool in data.get("tools", []):
            if tool["name"] == name:
                if enabled is not None:
                    tool["enabled"] = enabled
                if add_to_memory is not None:
                    tool["add_to_memory"] = add_to_memory
                self._write_tool_index(data)
                return True
        
        return False
    
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
            created_at: 创建时间（可选，默认当前时间）
        
        Returns:
            记忆 ID
        """
        memory_id = str(uuid.uuid4())[:8]
        now = created_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
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
        
        data = self._read_memory_index()
        data["memories"].append({
            "id": memory_id,
            "content": content,
            "memory_type": memory_type,
            "importance": importance,
            "tags": tags or [],
            "created_at": now
        })
        self._write_memory_index(data)
        
        logger.info(f"记忆已保存: {memory_id}")
        return memory_id
    
    def _add_memories_to_db(self, entries: List[Dict]) -> bool:
        """
        批量写入记忆到向量数据库（内部方法）
        
        Args:
            entries: 已包含 embedding 的记忆条目列表，每个条目包含：
                - id: 记忆 ID
                - content: 记忆内容
                - embedding: 嵌入向量
                - memory_type: 记忆类型
                - importance: 重要性评分
                - tags: 标签列表
                - created_at: 创建时间
        
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
    
    async def save_batch(
        self,
        items: List[Dict[str, Any]]
    ) -> List[str]:
        """
        批量保存记忆（高性能版本）
        
        相比逐条调用 save()，批量插入具有以下优势：
        - 批量获取嵌入向量，减少 API 调用次数
        - 批量写入向量数据库，减少 I/O 操作
        - 一次性更新 JSON 索引文件，避免重复读写
        
        Args:
            items: 记忆条目列表，每个条目包含：
                - content: 记忆内容（必需）
                - memory_type: 记忆类型（默认 conversation）
                - importance: 重要性评分（默认 5）
                - tags: 标签列表（默认 []）
                - created_at: 创建时间（可选，默认当前时间）
        
        Returns:
            记忆 ID 列表
        """
        if not items:
            return []
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        memory_ids = [str(uuid.uuid4())[:8] for _ in items]
        contents = [item.get("content", "") for item in items]
        
        if self.memories_table is not None:
            embeddings = await self._embed_batch(contents)
            
            entries = []
            for i, item in enumerate(items):
                embedding = embeddings[i] if i < len(embeddings) else []
                if embedding:
                    entries.append({
                        "id": memory_ids[i],
                        "content": item.get("content", ""),
                        "embedding": embedding,
                        "memory_type": item.get("memory_type", "conversation"),
                        "importance": item.get("importance", 5),
                        "tags": item.get("tags", []),
                        "created_at": item.get("created_at", now)
                    })
            
            self._add_memories_to_db(entries)
        
        data = self._read_memory_index()
        for i, item in enumerate(items):
            data["memories"].append({
                "id": memory_ids[i],
                "content": item.get("content", ""),
                "memory_type": item.get("memory_type", "conversation"),
                "importance": item.get("importance", 5),
                "tags": item.get("tags", []),
                "created_at": item.get("created_at", now)
            })
        self._write_memory_index(data)
        
        logger.info(f"批量保存记忆完成: {len(memory_ids)} 条")
        return memory_ids
    
    async def search(
        self,
        query: str,
        search_type: str = "all",
        top_k: int = 10,
        tags: List[str] = None,
        category: str = None,
        distance_threshold: float = 1.0
    ) -> Dict[str, List[Dict]]:
        """
        统一搜索
        
        Args:
            query: 搜索查询
            search_type: 搜索范围（all/memory/tool）
            top_k: 返回数量
            tags: 标签过滤（仅工具）
            category: 分类过滤（仅工具）
            distance_threshold: L2 距离阈值，距离越小越相似，默认 1.0
        
        Returns:
            {"memories": [...], "tools": [...]}
        """
        query_embedding = await self._embed(query)
        results = {"memories": [], "tools": []}
        
        if not query_embedding:
            return results
        
        if search_type in ["all", "memory"] and self.memories_table is not None:
            try:
                rows = self.memories_table.search(query_embedding).limit(top_k * 2).to_list()
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
                        "created_at": r.get("created_at", ""),
                        "_distance": distance
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
                    if distance > distance_threshold:
                        continue
                    
                    tool_tags = r.get("tags", [])
                    tool_category = r.get("category", "")
                    
                    if tags and not any(t in tool_tags for t in tags):
                        continue
                    if category and tool_category != category:
                        continue
                    
                    tool_def = json5.loads(r.get("tool_definition", "{}"))
                    tool_def["_distance"] = distance
                    results["tools"].append(tool_def)
                    self._increment_query_count(r["name"])
                    
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
            if self.memories_table is not None:
                self.memories_table.delete(f"id = '{memory_id}'")
            data = self._read_memory_index()
            data["memories"] = [m for m in data["memories"] if m.get("id") != memory_id]
            self._write_memory_index(data)
            return True
        except Exception as e:
            logger.error(f"删除记忆失败: {e}")
            return False
    
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
            top_k: 返回数量，默认 10
            full: 是否返回完整内容，默认 True
            order: 排序方式，desc(最近的在前) / asc(最早的在前)，默认 desc
            max_content_length: 内容截断长度（仅当 full=False 时生效）
        
        Returns:
            {"total_count": N, "returned_count": M, "memories": [...]}
        """
        if self.memories_table is None:
            return {"total_count": 0, "returned_count": 0, "memories": []}
        
        try:
            df = self.memories_table.to_pandas()
            columns_to_keep = ["id", "content", "memory_type", "importance", "tags", "created_at"]
            df_filtered = df[[col for col in columns_to_keep if col in df.columns]]
            all_rows = df_filtered.to_dict('records')
            total_count = len(all_rows)
            
            reverse_order = (order == "desc")
            sorted_rows = sorted(
                all_rows,
                key=lambda x: x.get("created_at", ""),
                reverse=reverse_order
            )
            
            limited_rows = sorted_rows[:top_k]
            
            memories = []
            for r in limited_rows:
                content = r.get("content", "")
                if not full and len(content) > max_content_length:
                    content = content[:max_content_length] + "..."
                
                tags = r.get("tags", [])
                if hasattr(tags, 'tolist'):
                    tags = tags.tolist()
                
                memories.append({
                    "id": r.get("id", ""),
                    "content": content,
                    "type": r.get("memory_type", "conversation"),
                    "importance": int(r.get("importance", 5)),
                    "tags": tags,
                    "created_at": r.get("created_at", "")
                })
            
            return {
                "total_count": total_count,
                "returned_count": len(memories),
                "memories": memories
            }
        except Exception as e:
            logger.error(f"列出记忆失败: {e}")
            return {"total_count": 0, "returned_count": 0, "memories": []}
    
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
            tool_type: 工具类型（skill/mcp_server/builtin）
            source: 工具来源路径
            enabled: 是否启用
            add_to_memory: 是否加入记忆索引
        
        Returns:
            工具名称
        """
        data = self._read_tool_index()
        
        if any(t["name"] == name for t in data["tools"]):
            logger.warning(f"工具已存在: {name}")
            return name
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tool = {
            "name": name,
            "tool_type": tool_type,
            "source": source,
            "enabled": enabled,
            "add_to_memory": add_to_memory,
            "query_count": 0,
            "created_at": now
        }
        
        if add_to_memory and enabled and self.tools_table:
            embedding = await self._embed(f"{name}: {description}")
            if embedding:
                entry = {
                    "id": f"{tool_type}:{name}",
                    "name": name,
                    "tool_type": tool_type,
                    "embedding": embedding,
                    "tool_definition": json5.dumps({
                        "name": name,
                        "description": description,
                        "tool_type": tool_type
                    }, ensure_ascii=False),
                    "query_count": 0
                }
                self.tools_table.add([entry])
        
        data["tools"].append(tool)
        self._write_tool_index(data)
        
        logger.info(f"工具已注册: {name}")
        return name
    
    async def unregister_tool(self, name: str) -> bool:
        """
        从索引移除工具
        
        Args:
            name: 工具名称（必须与系统工具名完全一致）
        
        Returns:
            是否移除成功
        """
        try:
            if self.tools_table is not None:
                self.tools_table.delete(f"name = '{name}'")
            
            data = self._read_tool_index()
            original_count = len(data["tools"])
            data["tools"] = [t for t in data["tools"] if t["name"] != name]
            
            if len(data["tools"]) < original_count:
                self._write_tool_index(data)
                logger.info(f"工具已移除: {name}")
                return True
            return False
        except Exception as e:
            logger.error(f"移除工具失败: {e}")
            return False
    
    def get_memory_tools(self) -> List[Dict]:
        """
        获取需要存入记忆索引的工具列表
        
        Returns:
            工具列表
        """
        data = self._read_tool_index()
        return [
            t for t in data.get("tools", [])
            if t.get("enabled", True) and t.get("add_to_memory", True)
        ]
    
    def compact(self, table_name: str = "all") -> bool:
        """
        压缩数据库表，减少碎片
        
        LanceDB 的 delete 操作不会立即释放磁盘空间，需要调用 compact。
        建议在大量删除操作后调用此方法。
        
        Args:
            table_name: 要压缩的表名（memories/tools/all），默认 all
        
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
    
    def get_all_ability_tags(self) -> List[str]:
        """
        获取所有能力标签（用于任务拆解阶段）
        
        从 tool_index.json 中提取所有 tags 字段，去重后返回。
        能力标签用于任务拆解阶段标注每个步骤所需的能力需求，
        执行阶段会根据能力标签通过 discover 工具动态匹配具体工具。
        
        Returns:
            能力标签列表，如 ["天气查询", "读取文件", "写入文件", ...]
        
        Example:
            >>> memory_system.get_all_ability_tags()
            ['天气', '查询', '实时信息', '日历', '计划', '技能', '安装', ...]
        """
        all_tags = set()
        data = self._read_tool_index()
        
        for tool in data.get("tools", []):
            if tool.get("enabled", True):
                tags = tool.get("tags", [])
                all_tags.update(tags)
                
        logger.info(f"get_all_ability_tags {len(all_tags)} 个能力标签: {all_tags}")
        return sorted(list(all_tags))
