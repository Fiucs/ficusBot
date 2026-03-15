#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :memory_store.py
# @Time      :2026/03/12
# @Author    :Ficus

"""
记忆存储模块 - MD文件存储层

负责记忆的MD文件读写和管理，支持：
- 按日期分文件存储（一天一个MD文件）
- 轻量索引（mtime + hash）检测文件变更
- 自动同步到向量数据库
- 从旧JSON格式迁移

核心方法:
    save: 保存单条记忆
    save_batch: 批量保存记忆
    delete: 删除指定ID的记忆
    get: 获取单条记忆
    list_all: 列出所有记忆
    sync_to_vector_db: 同步文件变更到向量库
    migrate_from_json: 从旧JSON迁移数据

Attributes:
    memories_path: MD文件存储路径
    index_file: 轻量索引文件路径
    _index: 内存中的索引数据
"""

import json
import hashlib
import re
import time
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from loguru import logger


class MemoryStore:
    """
    记忆存储类 - 负责MD文件的读写和管理
    
    使用按日期分文件的MD格式存储记忆，每条记忆包含：
    - id: 唯一标识
    - content: 记忆内容
    - memory_type: 记忆类型
    - importance: 重要性评分
    - tags: 标签列表
    - created_at: 创建时间
    
    文件结构:
        memories/
        ├── 2026-03-06.md      # 一天一个文件
        ├── 2026-03-08.md
        └── index.json         # 轻量索引
    
    MD格式示例:
        # 记忆 - 2026-03-12
        
        ## f80e6557
        - **类型**: fact
        - **重要度**: 5/10
        - **标签**: Vue3, TailwindCSS
        - **创建时间**: 2026-03-12 10:00:00
        
        Vue 3 + Tailwind CSS 轻量级框架推荐...
        
        ---
    
    Attributes:
        memories_path: MD文件存储路径
        index_file: 轻量索引文件路径
        _index: 内存中的索引数据
    """
    
    def __init__(self, index_path: Path):
        """
        初始化记忆存储
        
        Args:
            index_path: 索引文件路径（memory_index目录）
        """
        self.index_path = index_path
        self.memories_path = index_path / "memories"
        self.memories_path.mkdir(parents=True, exist_ok=True)
        
        self.index_file = self.memories_path / "index.json"
        self._index = self._load_index()
        
        # 检查是否需要迁移旧数据
        # old_json_file = index_path / "memory_index.json"
        # if old_json_file.exists() and not self._index.get("migrated", False):
        #     self.migrate_from_json(old_json_file)
        
        # 写入锁集合（用于区分 LLM 写入和用户编辑）
        self._writing_locks: set = set()
        
        logger.info(f"记忆存储初始化完成: {self.memories_path}")
    
    def is_writing(self, file_name: str) -> bool:
        """
        检查是否正在写入（由 LLM 触发）
        
        用于 watchdog 区分 LLM 写入和用户编辑
        
        Args:
            file_name: 文件名
        
        Returns:
            是否正在写入
        """
        return file_name in self._writing_locks
    
    def acquire_write_lock(self, file_name: str):
        """
        获取写入锁 - LLM 写入前调用
        
        Args:
            file_name: 要锁定的文件名
        """
        self._writing_locks.add(file_name)
        logger.debug(f"[MemoryStore] 获取写入锁: {file_name}")
    
    def release_write_lock(self, file_name: str):
        """
        释放写入锁 - LLM 写入后调用
        
        Args:
            file_name: 要释放的文件名
        """
        self._writing_locks.discard(file_name)
        logger.debug(f"[MemoryStore] 释放写入锁: {file_name}")
    
    def _load_index(self) -> Dict:
        """
        加载轻量索引
        
        Returns:
            索引数据字典
        """
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"加载索引文件失败: {e}")
        
        return {
            "version": "1.0",
            "updated_at": "",
            "migrated": False,
            "files": {}
        }
    
    def _save_index(self):
        """保存轻量索引到文件"""
        self._index["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump(self._index, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存索引文件失败: {e}")
    
    def _compute_hash(self, content: str) -> str:
        """
        计算内容哈希
        
        Args:
            content: 记忆内容
        
        Returns:
            8位哈希字符串
        """
        return hashlib.md5(content.encode()).hexdigest()[:8]
    
    def _get_date_from_timestamp(self, timestamp: str) -> str:
        """
        从时间戳提取日期
        
        Args:
            timestamp: 时间字符串（如 "2026-03-12 10:00:00"）
        
        Returns:
            日期字符串（如 "2026-03-12"）
        """
        try:
            return timestamp.split()[0]
        except:
            return datetime.now().strftime("%Y-%m-%d")
    
    def _format_memory_to_md(self, memory: Dict) -> str:
        """
        将记忆格式化为MD字符串
        
        Args:
            memory: 记忆字典
        
        Returns:
            MD格式字符串
        """
        tags_str = ", ".join(memory.get("tags", []))
        return f"""## {memory['id']}
- **类型**: {memory.get('memory_type', 'conversation')}
- **重要度**: {memory.get('importance', 5)}/10
- **标签**: {tags_str}
- **创建时间**: {memory.get('created_at', '')}

{memory['content']}

---

"""
    
    def _parse_md_file(self, md_file: Path) -> Dict[str, Dict]:
        """
        解析MD文件为记忆字典
        
        只解析标准格式（有 ## ID）的记录
        
        Args:
            md_file: MD文件路径
        
        Returns:
            记忆ID到记忆字典的映射
        """
        records = {}
        
        try:
            content = md_file.read_text(encoding='utf-8')
        except Exception as e:
            logger.error(f"读取MD文件失败 {md_file}: {e}")
            return records
        
        # 匹配标准格式（有 ## ID）
        # 匹配 ## ID 开头，直到下一个 ## ID 或文件结束
        pattern_with_id = r'##\s*(\S+)\s*\n(.*?)(?=\n##\s|\Z)'
        matches = list(re.finditer(pattern_with_id, content, re.DOTALL))
        
        if not matches:
            # 如果没有匹配到任何记录，尝试更宽松的匹配
            # 可能是文件格式有问题
            logger.warning(f"[parse_md] 未匹配到任何标准记录: {md_file.name}")
        
        for match in matches:
            memory_id = match.group(1).strip()
            block = match.group(2).strip()
            
            memory = self._parse_memory_block(memory_id, block)
            if memory:
                records[memory_id] = memory
        
        return records
    
    def _parse_memory_block(self, memory_id: str, block: str) -> Optional[Dict]:
        """
        解析单个记忆块
        
        Args:
            memory_id: 记忆ID
            block: 记忆块内容
        
        Returns:
            记忆字典或None
        """
        try:
            # 提取元数据
            memory_type_match = re.search(r'\*\*类型\*\*:\s*(\S+)', block)
            importance_match = re.search(r'\*\*重要度\*\*:\s*(\d+)', block)
            tags_match = re.search(r'\*\*标签\*\*:\s*(.*?)(?:\n|$)', block)
            created_at_match = re.search(r'\*\*创建时间\*\*:\s*(.+?)(?:\n|$)', block)
            
            # 提取内容（在元数据之后，---之前）
            content_match = re.search(r'\*\*创建时间\*\*:.+?\n\n(.+?)(?:\n---|\Z)', block, re.DOTALL)
            
            memory_type = memory_type_match.group(1) if memory_type_match else "conversation"
            importance = int(importance_match.group(1)) if importance_match else 5
            tags_str = tags_match.group(1).strip() if tags_match else ""
            tags = [t.strip() for t in tags_str.split(",") if t.strip()]
            created_at = created_at_match.group(1).strip() if created_at_match else ""
            content = content_match.group(1).strip() if content_match else ""
            
            return {
                "id": memory_id,
                "content": content,
                "memory_type": memory_type,
                "importance": importance,
                "tags": tags,
                "created_at": created_at
            }
        except Exception as e:
            logger.warning(f"解析记忆块失败 {memory_id}: {e}")
            return None
    
    def _get_md_file_path(self, date_str: str) -> Path:
        """
        获取指定日期的MD文件路径
        
        Args:
            date_str: 日期字符串（如 "2026-03-12"）
        
        Returns:
            MD文件路径
        """
        return self.memories_path / f"{date_str}.md"
    
    def save(self, memory: Dict) -> str:
        """
        保存单条记忆
        
        将记忆追加到对应日期的MD文件中
        
        Args:
            memory: 记忆字典，包含 id, content, memory_type, importance, tags, created_at
        
        Returns:
            记忆ID
        """
        memory_id = memory.get("id")
        if not memory_id:
            import uuid
            memory_id = str(uuid.uuid4())[:8]
            memory["id"] = memory_id
        
        date_str = self._get_date_from_timestamp(memory.get("created_at", ""))
        md_file = self._get_md_file_path(date_str)
        
        # 格式化记忆为MD
        md_content = self._format_memory_to_md(memory)
        
        # 追加到文件
        try:
            if not md_file.exists():
                # 新文件，添加标题
                header = f"# 记忆 - {date_str}\n\n"
                md_file.write_text(header + md_content, encoding='utf-8')
            else:
                # 追加到现有文件
                with open(md_file, 'a', encoding='utf-8') as f:
                    f.write(md_content)
            
            # 更新索引
            self._update_index_for_memory(date_str, memory)
            
            logger.info(f"记忆已保存: {memory_id} -> {md_file.name}")
            return memory_id
            
        except Exception as e:
            logger.error(f"保存记忆失败 {memory_id}: {e}")
            raise
    
    def save_batch(self, memories: List[Dict]) -> List[str]:
        """
        批量保存记忆
        
        按日期分组，批量追加到对应文件
        
        Args:
            memories: 记忆字典列表
        
        Returns:
            记忆ID列表
        """
        if not memories:
            return []
        
        # 按日期分组
        date_groups: Dict[str, List[Dict]] = {}
        memory_ids = []
        
        for memory in memories:
            # 确保有ID
            if not memory.get("id"):
                import uuid
                memory["id"] = str(uuid.uuid4())[:8]
            
            memory_id = memory["id"]
            memory_ids.append(memory_id)
            
            date_str = self._get_date_from_timestamp(memory.get("created_at", ""))
            if date_str not in date_groups:
                date_groups[date_str] = []
            date_groups[date_str].append(memory)
        
        # 按日期批量写入
        for date_str, group_memories in date_groups.items():
            md_file = self._get_md_file_path(date_str)
            
            # 格式化所有记忆
            md_content = ""
            for memory in group_memories:
                md_content += self._format_memory_to_md(memory)
            
            try:
                if not md_file.exists():
                    header = f"# 记忆 - {date_str}\n\n"
                    md_file.write_text(header + md_content, encoding='utf-8')
                else:
                    with open(md_file, 'a', encoding='utf-8') as f:
                        f.write(md_content)
                
                # 更新索引
                for memory in group_memories:
                    self._update_index_for_memory(date_str, memory)
                
                logger.info(f"批量保存记忆: {len(group_memories)} 条 -> {md_file.name}")
                
            except Exception as e:
                logger.error(f"批量保存记忆失败 {date_str}: {e}")
                raise
        
        return memory_ids
    
    def _update_index_for_memory(self, date_str: str, memory: Dict):
        """
        更新索引中的单条记忆
        
        Args:
            date_str: 日期字符串
            memory: 记忆字典
        """
        file_name = f"{date_str}.md"
        
        if file_name not in self._index["files"]:
            self._index["files"][file_name] = {
                "mtime": 0,
                "records": {}
            }
        
        # 计算哈希
        content_hash = self._compute_hash(memory.get("content", ""))
        self._index["files"][file_name]["records"][memory["id"]] = content_hash
        
        # 保存索引
        self._save_index()
    
    def delete(self, memory_id: str) -> bool:
        """
        删除指定ID的记忆
        
        从MD文件中删除对应章节，并更新索引
        
        Args:
            memory_id: 记忆ID
        
        Returns:
            是否删除成功
        """
        # 查找记忆所在的文件
        for file_name, file_info in self._index.get("files", {}).items():
            if memory_id in file_info.get("records", {}):
                md_file = self.memories_path / file_name
                
                if not md_file.exists():
                    logger.warning(f"MD文件不存在: {md_file}")
                    return False
                
                try:
                    # 读取文件内容
                    content = md_file.read_text(encoding='utf-8')
                    
                    # 删除对应章节
                    pattern = rf'##\s*{memory_id}\s*\n.*?---\s*\n'
                    new_content = re.sub(pattern, '', content, flags=re.DOTALL)
                    
                    # 写回文件
                    md_file.write_text(new_content, encoding='utf-8')
                    
                    # 更新索引
                    del self._index["files"][file_name]["records"][memory_id]
                    self._save_index()
                    
                    logger.info(f"记忆已删除: {memory_id}")
                    return True
                    
                except Exception as e:
                    logger.error(f"删除记忆失败 {memory_id}: {e}")
                    return False
        
        logger.warning(f"未找到记忆: {memory_id}")
        return False
    
    def update(self, memory_id: str, updates: Dict[str, Any]) -> Optional[Dict]:
        """
        更新指定ID的记忆
        
        从MD文件中查找并更新对应章节，保留未提供的字段不变
        
        Args:
            memory_id: 记忆ID
            updates: 更新字段字典，可包含 content, memory_type, importance, tags
        
        Returns:
            更新后的记忆字典，未找到返回None
        """
        # 查找记忆所在的文件
        for file_name, file_info in self._index.get("files", {}).items():
            if memory_id in file_info.get("records", {}):
                md_file = self.memories_path / file_name
                
                if not md_file.exists():
                    logger.warning(f"MD文件不存在: {md_file}")
                    return None
                
                try:
                    # 解析当前文件获取原记忆
                    records = self._parse_md_file(md_file)
                    old_memory = records.get(memory_id)
                    
                    if not old_memory:
                        logger.warning(f"未在MD文件中找到记忆: {memory_id}")
                        return None
                    
                    # 构建更新后的记忆（保留原值，更新提供的字段）
                    updated_memory = {
                        "id": memory_id,
                        "content": updates.get("content", old_memory["content"]),
                        "memory_type": updates.get("memory_type", old_memory["memory_type"]),
                        "importance": updates.get("importance", old_memory["importance"]),
                        "tags": updates.get("tags", old_memory["tags"]),
                        "created_at": old_memory["created_at"]  # 保持原创建时间
                    }
                    
                    # 读取文件内容
                    content = md_file.read_text(encoding='utf-8')
                    
                    # 格式化新的记忆块
                    new_memory_block = self._format_memory_to_md(updated_memory)
                    
                    # 替换旧的记忆块
                    pattern = rf'##\s*{memory_id}\s*\n.*?---\s*\n'
                    new_content = re.sub(pattern, new_memory_block, content, flags=re.DOTALL)
                    
                    # 写回文件
                    md_file.write_text(new_content, encoding='utf-8')
                    
                    # 更新索引中的哈希
                    new_hash = self._compute_hash(updated_memory["content"])
                    self._index["files"][file_name]["records"][memory_id] = new_hash
                    self._save_index()
                    
                    logger.info(f"记忆已更新: {memory_id}")
                    return updated_memory
                    
                except Exception as e:
                    logger.error(f"更新记忆失败 {memory_id}: {e}")
                    return None
        
        logger.warning(f"未找到记忆: {memory_id}")
        return None
    
    def get(self, memory_id: str) -> Optional[Dict]:
        """
        获取单条记忆
        
        Args:
            memory_id: 记忆ID
        
        Returns:
            记忆字典或None
        """
        # 查找记忆所在的文件
        for file_name, file_info in self._index.get("files", {}).items():
            if memory_id in file_info.get("records", {}):
                md_file = self.memories_path / file_name
                records = self._parse_md_file(md_file)
                return records.get(memory_id)
        
        return None
    
    def list_all(self) -> List[Dict]:
        """
        列出所有记忆
        
        Returns:
            记忆字典列表
        """
        all_memories = []
        
        # 遍历所有MD文件
        for md_file in sorted(self.memories_path.glob("*.md")):
            if md_file.name == "index.json":
                continue
            
            records = self._parse_md_file(md_file)
            all_memories.extend(records.values())
        
        # 按创建时间排序
        all_memories.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        return all_memories
    
    def detect_changes(self) -> Dict[str, List]:
        """
        检测MD文件的变动
        
        对比当前文件状态和索引，返回新增、删除、修改的记录。
        不更新索引，调用方需要自行调用 sync_to_vector_db() 或 update_index() 来更新索引。
        
        Returns:
            变更记录 {
                "added": [...],      # 新增的记忆列表
                "deleted": [...],    # 删除的记忆ID列表
                "modified": [...],   # 修改的记忆列表
                "files_changed": [...]  # 变更的文件名列表
            }
        """
        changes = {"added": [], "deleted": [], "modified": [], "files_changed": []}
        
        current_files = set()
        
        for md_file in self.memories_path.glob("*.md"):
            if md_file.name == "index.json":
                continue
            
            file_name = md_file.name
            current_files.add(file_name)
            current_mtime = md_file.stat().st_mtime
            
            stored_info = self._index.get("files", {}).get(file_name, {})
            stored_mtime = stored_info.get("mtime", 0)
            
            if current_mtime == stored_mtime:
                continue
            
            changes["files_changed"].append(file_name)
            
            current_records = self._parse_md_file(md_file)
            current_ids = set(current_records.keys())
            
            old_records = stored_info.get("records", {})
            old_ids = set(old_records.keys())
            
            for rid in current_ids - old_ids:
                changes["added"].append(current_records[rid])
            
            for rid in old_ids - current_ids:
                changes["deleted"].append(rid)
            
            for rid in current_ids & old_ids:
                new_hash = self._compute_hash(current_records[rid]["content"])
                if new_hash != old_records[rid]:
                    changes["modified"].append(current_records[rid])
            
            if not changes["added"] and not changes["deleted"] and not changes["modified"]:
                logger.warning(f"[detect_changes] 文件 {file_name} 已修改但未检测到标准记录变动，" 
                              f"尝试修复无ID记录...")
                
                self._rewrite_manual_ids_to_md(file_name)
                
                current_records = self._parse_md_file(md_file)
                current_ids = set(current_records.keys())
                
                for rid in current_ids - old_ids:
                    changes["added"].append(current_records[rid])
                
                for rid in old_ids - current_ids:
                    changes["deleted"].append(rid)
                
                for rid in current_ids & old_ids:
                    new_hash = self._compute_hash(current_records[rid]["content"])
                    if new_hash != old_records[rid]:
                        changes["modified"].append(current_records[rid])
                
                if changes["added"] or changes["deleted"] or changes["modified"]:
                    logger.info(f"[detect_changes] 修复后检测到变动: 新增={len(changes['added'])}, "
                               f"删除={len(changes['deleted'])}, 修改={len(changes['modified'])}")
        
        indexed_files = set(self._index.get("files", {}).keys())
        deleted_files = indexed_files - current_files
        
        for file_name in deleted_files:
            stored_info = self._index.get("files", {}).get(file_name, {})
            old_records = stored_info.get("records", {})
            
            for rid in old_records.keys():
                changes["deleted"].append(rid)
            
            changes["files_changed"].append(file_name)
            logger.info(f"[detect_changes] 检测到文件删除: {file_name}, 包含 {len(old_records)} 条记录")
        
        total_changes = len(changes["added"]) + len(changes["deleted"]) + len(changes["modified"])
        if total_changes > 0:
            logger.info(f"检测到变动: 新增={len(changes['added'])}, 删除={len(changes['deleted'])}, 修改={len(changes['modified'])}, 文件={changes['files_changed']}")
        
        return changes
    
    def update_index(self, changes: Dict[str, List] = None):
        """
        更新索引，标记变动已处理
        
        同时为手动添加的无ID记录回写ID到MD文件
        
        Args:
            changes: detect_changes() 返回的变更记录，如果为None则重新扫描所有文件
        """
        # 先回写手动添加记录的ID到MD文件
        if changes:
            for file_name in changes.get("files_changed", []):
                self._rewrite_manual_ids_to_md(file_name)
        
        if changes is None:
            # 重新扫描所有文件并更新索引
            for md_file in self.memories_path.glob("*.md"):
                if md_file.name == "index.json":
                    continue
                
                file_name = md_file.name
                current_mtime = md_file.stat().st_mtime
                current_records = self._parse_md_file(md_file)
                
                self._index["files"][file_name] = {
                    "mtime": current_mtime,
                    "records": {
                        rid: self._compute_hash(r["content"])
                        for rid, r in current_records.items()
                    }
                }
        else:
            # 只更新变更的文件
            for file_name in changes.get("files_changed", []):
                md_file = self.memories_path / file_name
                if not md_file.exists():
                    # 文件被删除，从索引中移除
                    if file_name in self._index["files"]:
                        del self._index["files"][file_name]
                    continue
                
                current_mtime = md_file.stat().st_mtime
                current_records = self._parse_md_file(md_file)
                
                self._index["files"][file_name] = {
                    "mtime": current_mtime,
                    "records": {
                        rid: self._compute_hash(r["content"])
                        for rid, r in current_records.items()
                    }
                }
        
        self._save_index()
        logger.info("索引已更新")
    
    def _rewrite_manual_ids_to_md(self, file_name: str):
        """
        检测并修复MD文件中的无ID记录
        
        按 --- 分隔符分割文件，为无ID的段落添加ID
        
        Args:
            file_name: MD文件名
        """
        md_file = self.memories_path / file_name
        if not md_file.exists():
            return
        
        try:
            content = md_file.read_text(encoding='utf-8')
            
            parts = re.split(r'---\s*\n*', content)
            if len(parts) < 2:
                return
            
            new_parts = [parts[0].rstrip()]  # 保留标题部分
            has_changes = False
            
            for part in parts[1:]:
                part = part.strip()
                if not part:
                    continue
                
                if part.startswith('## '):
                    new_parts.append(part)
                elif part.startswith('- **类型**:'):
                    memory_id = f"manual_{uuid.uuid4().hex[:8]}"
                    new_part = f"## {memory_id}\n{part}"
                    new_parts.append(new_part)
                    logger.info(f"[rewrite] 为无ID记录生成ID: {memory_id}")
                    has_changes = True
                else:
                    new_parts.append(part)
            
            if not has_changes:
                return
            
            new_content = '\n\n---\n\n'.join(new_parts) + '\n'
            
            self.acquire_write_lock(file_name)
            try:
                md_file.write_text(new_content, encoding='utf-8')
                logger.info(f"[rewrite] 已更新MD文件: {file_name}")
            finally:
                time.sleep(0.3)
                self.release_write_lock(file_name)
        
        except Exception as e:
            logger.error(f"[rewrite] 修复MD文件失败 {file_name}: {e}")
    
    def sync_to_vector_db(self, vector_table) -> Dict[str, List]:
        """
        同步文件变更到向量数据库
        
        检测新增、删除、修改的记录，并同步到向量库
        
        Args:
            vector_table: 向量数据库表
        
        Returns:
            变更记录 {"added": [], "deleted": [], "modified": []}
        """
        changes = {"added": [], "deleted": [], "modified": []}
        
        # 遍历所有MD文件
        for md_file in self.memories_path.glob("*.md"):
            if md_file.name == "index.json":
                continue
            
            file_name = md_file.name
            current_mtime = md_file.stat().st_mtime
            
            # 获取存储的mtime
            stored_info = self._index.get("files", {}).get(file_name, {})
            stored_mtime = stored_info.get("mtime", 0)
            
            # 文件未修改，跳过
            if current_mtime == stored_mtime:
                continue
            
            # 解析当前文件中的所有记录
            current_records = self._parse_md_file(md_file)
            current_ids = set(current_records.keys())
            
            # 获取索引中记录的旧状态
            old_records = stored_info.get("records", {})
            old_ids = set(old_records.keys())
            
            # 检测新增
            for rid in current_ids - old_ids:
                changes["added"].append(current_records[rid])
            
            # 检测删除
            for rid in old_ids - current_ids:
                changes["deleted"].append(rid)
            
            # 检测修改（ID相同但哈希不同）
            for rid in current_ids & old_ids:
                new_hash = self._compute_hash(current_records[rid]["content"])
                if new_hash != old_records[rid]:
                    changes["modified"].append(current_records[rid])
            
            # 更新索引
            self._index["files"][file_name] = {
                "mtime": current_mtime,
                "records": {
                    rid: self._compute_hash(r["content"])
                    for rid, r in current_records.items()
                }
            }
        
        # 应用变更到向量数据库
        self._apply_changes_to_vector_db(vector_table, changes)
        
        # 保存索引
        self._save_index()
        
        total_changes = len(changes["added"]) + len(changes["deleted"]) + len(changes["modified"])
        if total_changes > 0:
            logger.info(f"同步到向量库: 新增={len(changes['added'])}, 删除={len(changes['deleted'])}, 修改={len(changes['modified'])}")
        
        return changes
    
    def _apply_changes_to_vector_db(self, vector_table, changes: Dict):
        """
        应用变更到向量数据库
        
        Args:
            vector_table: 向量数据库表
            changes: 变更记录
        """
        if vector_table is None:
            return
        
        try:
            # 删除记录
            for rid in changes["deleted"]:
                vector_table.delete(f"id = '{rid}'")
            
            # 修改记录（先删后插，需要重新计算embedding）
            for record in changes["modified"]:
                vector_table.delete(f"id = '{record['id']}'")
                # 注意：修改后的记录需要重新计算embedding后插入
                # 这里只删除，由调用方重新插入
            
            # 新增记录（同样需要embedding）
            # 由调用方处理
            
        except Exception as e:
            logger.error(f"应用变更到向量库失败: {e}")
    
    def migrate_from_json(self, json_file: Path):
        """
        从旧JSON格式迁移数据到MD格式
        
        Args:
            json_file: 旧JSON文件路径
        """
        logger.info(f"开始从JSON迁移数据: {json_file}")
        
        try:
            import json5
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json5.load(f)
            
            memories = data.get("memories", [])
            if not memories:
                logger.info("JSON中没有记忆数据需要迁移")
                return
            
            # 按日期分组
            date_groups: Dict[str, List[Dict]] = {}
            for memory in memories:
                created_at = memory.get("created_at", "")
                date_str = self._get_date_from_timestamp(created_at)
                
                if date_str not in date_groups:
                    date_groups[date_str] = []
                date_groups[date_str].append(memory)
            
            # 为每个日期创建MD文件
            for date_str, group_memories in date_groups.items():
                md_file = self._get_md_file_path(date_str)
                
                # 构建MD内容
                md_content = f"# 记忆 - {date_str}\n\n"
                for memory in group_memories:
                    md_content += self._format_memory_to_md(memory)
                
                # 写入文件
                md_file.write_text(md_content, encoding='utf-8')
                
                # 更新索引
                self._index["files"][f"{date_str}.md"] = {
                    "mtime": md_file.stat().st_mtime,
                    "records": {
                        m["id"]: self._compute_hash(m.get("content", ""))
                        for m in group_memories
                    }
                }
                
                logger.info(f"迁移 {len(group_memories)} 条记忆到 {md_file.name}")
            
            # 标记已迁移
            self._index["migrated"] = True
            self._save_index()
            
            # 备份旧文件
            backup_file = json_file.with_suffix('.json.bak')
            json_file.rename(backup_file)
            logger.info(f"旧JSON文件已备份: {backup_file}")
            
            logger.info(f"数据迁移完成，共迁移 {len(memories)} 条记忆")
            
        except Exception as e:
            logger.error(f"数据迁移失败: {e}")
            raise
