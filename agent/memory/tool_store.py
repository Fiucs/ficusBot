#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :tool_store.py
# @Time      :2026/03/12
# @Author    :Ficus

"""
工具存储模块

管理工具的向量索引和检索，支持：
- 工具的语义搜索
- 工具的注册/注销
- 工具配置管理
- 热点工具自动提升

核心方法:
    search_tools: 搜索单个查询
    search_tools_batch: 批量搜索（自动去重）
    register_tool: 注册工具
    unregister_tool: 注销工具
    process_tools: 处理工具列表（过滤分类）
    sync_memory_tools: 同步工具到向量索引

Attributes:
    tools_table: LanceDB 工具表
    tools_schema: 工具表 Schema
    index_path: 索引文件路径
    hot_threshold: 热点工具阈值
    hot_tool_limit: 热点工具上限
"""

import json
import json5
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path

from loguru import logger


class ToolStore:
    """
    工具存储类
    
    管理工具的向量索引和检索。
    
    核心方法:
        search_tools: 搜索单个查询
        search_tools_batch: 批量搜索（自动去重）
        register_tool: 注册工具
        unregister_tool: 注销工具
        process_tools: 处理工具列表（过滤分类）
        sync_memory_tools: 同步工具到向量索引
    
    Attributes:
        tools_table: LanceDB 工具表
        tools_schema: 工具表 Schema
        index_path: 索引文件路径
        hot_threshold: 热点工具阈值
        hot_tool_limit: 热点工具上限
    """
    
    def __init__(
        self,
        tools_table,
        tools_schema,
        index_path: Path,
        hot_threshold: int = 10,
        hot_tool_limit: int = 5,
        embedding_service=None
    ):
        """
        初始化工具存储
        
        Args:
            tools_table: LanceDB 工具表
            tools_schema: 工具表 Schema
            index_path: 索引文件路径
            hot_threshold: 热点工具阈值
            hot_tool_limit: 热点工具上限
            embedding_service: 嵌入服务实例
        """
        self.tools_table = tools_table
        self.tools_schema = tools_schema
        self.index_path = index_path
        self.hot_threshold = hot_threshold
        self.hot_tool_limit = hot_tool_limit
        self._embedding = embedding_service
    
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
    
    async def _embed(self, text: str) -> List[float]:
        """获取嵌入向量"""
        if self._embedding is None:
            return []
        return await self._embedding.embed(text)
    
    async def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量获取嵌入向量"""
        if self._embedding is None:
            return [[] for _ in texts]
        return await self._embedding.embed_batch(texts)
    
    def process_tools(self, all_tools: List[Dict]) -> Dict[str, Any]:
        """
        处理工具列表（核心方法）
        
        根据索引文件配置处理工具：
        - enabled=false → 从工具列表移除
        - enabled=true, add_to_memory=false 或未配置 → 保留在工具列表（常驻）
        - enabled=true, add_to_memory=true → 存入记忆索引并移除
        
        特殊处理：
        - category=core 的工具始终常驻
        
        匹配规则：
        - name 必须与系统工具名完全一致
        
        Args:
            all_tools: 系统加载的所有工具列表
        
        Returns:
            {
                "memory_tools": List[Dict],
                "keep_tools": List[Dict]
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
                add_to_memory = index_entry.get("add_to_memory", False)
                category = index_entry.get("category", "")
                
                if not enabled:
                    disabled_tools.append(tool_name)
                    logger.debug(f"  - 工具已禁用: {tool_name}")
                    continue
                
                if category == "core":
                    keep_tools.append(tool)
                    logger.debug(f"  - 核心工具保留常驻: {tool_name}")
                elif add_to_memory:
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
    
    async def sync_memory_tools(self, tools: List[Dict], db):
        """
        异步同步工具到记忆索引
        
        直接存储完整的 Function Call 定义，不做映射
        使用全量同步（重建表），避免碎片产生
        
        Args:
            tools: 需要存入记忆索引的工具列表
            db: LanceDB 数据库连接
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
            capability = index_entry.get("capability", "")
            keywords = " ".join(index_entry.get("keywords", []))
            tags = " ".join(index_entry.get("tags", []))

            text_parts = [f"{name}: {desc}"]
            if capability:
                text_parts.append(capability)
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
        
        self.tools_table = db.create_table("tools", schema=self.tools_schema, mode="overwrite")
        if entries:
            self.tools_table.add(entries)
        logger.info(f"记忆索引同步完成，共 {len(entries)} 个工具")
    
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
    
    def get_all_capabilities(self) -> List[str]:
        """
        获取所有能力标签（用于任务拆解阶段）

        从 tool_index.json 中提取所有 capability 字段，去重后返回。
        能力标签用于任务拆解阶段标注每个步骤所需的能力需求，
        执行阶段会根据能力标签通过向量搜索动态匹配具体工具。

        Returns:
            能力标签列表，如 ["天气查询", "网络搜索", "文件读取", "文件写入", ...]
        """
        all_capabilities = set()
        data = self._read_tool_index()

        for tool in data.get("tools", []):
            if tool.get("enabled", True):
                capability = tool.get("capability", "")
                if capability:
                    all_capabilities.add(capability)

        logger.info(f"get_all_capabilities {len(all_capabilities)} 个能力: {all_capabilities}")
        return sorted(list(all_capabilities))
