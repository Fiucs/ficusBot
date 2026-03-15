#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
同步向量库和MD文件

检查并修复向量库与MD文件之间的不同步问题：
1. 删除向量库中存在但MD文件中不存在的记录
2. 更新索引文件
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from datetime import datetime

from loguru import logger


def sync_memory_db():
    """
    同步向量库和MD文件
    """
    workspace_root = Path(__file__).parent.parent / ".ficsbot" / "workspace"
    memories_path = workspace_root / "memory" / "memory_index" / "memories"
    vector_db_path = workspace_root / "memory" / "vector_db"
    index_file = memories_path / "index.json"
    
    import json
    import lancedb
    
    logger.info(f"记忆文件路径: {memories_path}")
    logger.info(f"向量库路径: {vector_db_path}")
    
    db = lancedb.connect(str(vector_db_path))
    memories_table = db.open_table("memories")
    
    vector_records = memories_table.search().limit(None).to_list()
    vector_ids = {r["id"] for r in vector_records}
    logger.info(f"向量库中记录数: {len(vector_ids)}")
    
    md_ids = set()
    md_records = {}
    
    from agent.memory.memory_store import MemoryStore
    
    memory_store = MemoryStore(workspace_root / "memory" / "memory_index")
    
    for md_file in memories_path.glob("*.md"):
        if md_file.name == "index.json":
            continue
        records = memory_store._parse_md_file(md_file)
        for rid, record in records.items():
            md_ids.add(rid)
            md_records[rid] = record
    
    logger.info(f"MD文件中记录数: {len(md_ids)}")
    
    only_in_vector = vector_ids - md_ids
    only_in_md = md_ids - vector_ids
    
    logger.info(f"仅在向量库中的记录: {len(only_in_vector)}")
    logger.info(f"仅在MD文件中的记录: {len(only_in_md)}")
    
    if only_in_vector:
        logger.info(f"需要从向量库删除的记录: {only_in_vector}")
        for rid in only_in_vector:
            try:
                memories_table.delete(f"id = '{rid}'")
                logger.info(f"已从向量库删除: {rid}")
            except Exception as e:
                logger.error(f"删除失败 {rid}: {e}")
    
    if only_in_md:
        logger.info(f"需要添加到向量库的记录: {only_in_md}")
        logger.info("这些记录将在下次搜索时自动同步")
    
    with open(index_file, 'r', encoding='utf-8') as f:
        index_data = json.load(f)
    
    current_files = set()
    for md_file in memories_path.glob("*.md"):
        if md_file.name == "index.json":
            continue
        current_files.add(md_file.name)
    
    indexed_files = set(index_data.get("files", {}).keys())
    deleted_files = indexed_files - current_files
    
    if deleted_files:
        logger.info(f"索引中存在但文件已删除: {deleted_files}")
        for file_name in deleted_files:
            del index_data["files"][file_name]
            logger.info(f"已从索引中移除: {file_name}")
    
    for file_name in current_files:
        md_file = memories_path / file_name
        records = memory_store._parse_md_file(md_file)
        
        if file_name not in index_data["files"]:
            index_data["files"][file_name] = {
                "mtime": md_file.stat().st_mtime,
                "records": {}
            }
        
        index_data["files"][file_name]["mtime"] = md_file.stat().st_mtime
        index_data["files"][file_name]["records"] = {
            rid: memory_store._compute_hash(r["content"])
            for rid, r in records.items()
        }
    
    index_data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(index_file, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    
    logger.info("索引文件已更新")
    
    logger.info("=" * 50)
    logger.info("同步完成!")
    logger.info(f"  - 向量库记录: {len(vector_ids)} -> {len(vector_ids) - len(only_in_vector)}")
    logger.info(f"  - MD文件记录: {len(md_ids)}")
    logger.info(f"  - 已删除多余向量: {len(only_in_vector)}")
    logger.info(f"  - 待添加向量: {len(only_in_md)}")


if __name__ == "__main__":
    sync_memory_db()
