#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :heartbeat_manager.py
# @Time      :2026/03/10
# @Author    :Ficus

"""
心跳状态机 - 管理当前任务执行状态和进度追踪

核心功能:
    - 维护全局唯一心跳状态
    - 记录当前任务执行进度
    - 支持断点续跑
    - 快速检测未完成任务

设计原则:
    - 全局单一心跳文件，简化查找逻辑
    - 心跳是"当前执行状态"，不是"历史记录"
    - 任务状态持久化到 tasks/heartbeat.json

使用示例:
    >>> manager = HeartbeatManager(workspace_root)
    >>> manager.init(task_id, task_tree)
    >>> heartbeat = manager.load()
    >>> manager.complete_step("step_1")
"""

import json
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

from loguru import logger
from colorama import Fore, Style


class HeartbeatManager:
    """
    心跳状态机（全局单一心跳）
    
    功能说明:
        - 维护全局唯一心跳状态
        - 记录当前任务执行进度
        - 支持断点续跑
    
    核心方法:
        - init: 初始化心跳状态（新任务）
        - load: 加载心跳状态
        - start_step: 开始执行步骤
        - complete_step: 完成步骤
        - fail_step: 步骤失败
        - clear: 清除心跳（任务完成或放弃）
    
    文件结构:
        workspace/tasks/heartbeat.json（全局唯一）
    """
    
    def __init__(self, workspace_root: str):
        """
        初始化心跳状态机
        
        Args:
            workspace_root: 工作区根目录
        """
        self.workspace_root = workspace_root
        self.tasks_dir = Path(workspace_root) / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.heartbeat_file = self.tasks_dir / "heartbeat.json"
        logger.info(f"{Fore.CYAN}心跳状态机初始化完成，心跳文件: {self.heartbeat_file}{Style.RESET_ALL}")
    
    def init(self, task_id: str, task_tree: Dict) -> bool:
        """
        初始化心跳状态（开始新任务）
        
        Args:
            task_id: 任务 ID
            task_tree: 任务树字典
        
        Returns:
            是否初始化成功
        """
        try:
            now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            
            heartbeat = {
                "task_id": task_id,
                "status": "pending",
                "current_step": None,
                "completed_steps": [],
                "started_steps": [],  # 新增：已开始的步骤（包括失败的）
                "progress": 0,
                "total_steps": task_tree.get("total_steps", 0),
                "started_at": now,
                "updated_at": now,
                "error_count": 0,
                "last_error": None
            }
            
            with open(self.heartbeat_file, "w", encoding="utf-8") as f:
                json.dump(heartbeat, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"{Fore.GREEN}[心跳状态] 心跳已初始化: {task_id}{Style.RESET_ALL}")
            return True
            
        except Exception as e:
            logger.error(f"{Fore.RED}[心跳状态] 初始化心跳失败: {e}{Style.RESET_ALL}")
            return False
    
    def load(self) -> Optional[Dict]:
        """
        加载心跳状态
        
        Returns:
            心跳状态字典，不存在则返回 None
        """
        try:
            if not self.heartbeat_file.exists():
                return None
            
            with open(self.heartbeat_file, "r", encoding="utf-8") as f:
                heartbeat = json.load(f)
            
            logger.debug(f"{Fore.CYAN}[心跳状态] 心跳已加载{Style.RESET_ALL}")
            return heartbeat
            
        except Exception as e:
            logger.error(f"{Fore.RED}[心跳状态] 加载心跳失败: {e}{Style.RESET_ALL}")
            return None
    
    def save(self, heartbeat: Dict) -> bool:
        """
        保存心跳状态
        
        Args:
            heartbeat: 心跳状态字典
        
        Returns:
            是否保存成功
        """
        try:
            heartbeat["updated_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            
            with open(self.heartbeat_file, "w", encoding="utf-8") as f:
                json.dump(heartbeat, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"{Fore.CYAN}[心跳状态] 心跳已保存{Style.RESET_ALL}")
            return True
            
        except Exception as e:
            logger.error(f"{Fore.RED}[心跳状态] 保存心跳失败: {e}{Style.RESET_ALL}")
            return False
    
    def start_step(self, step_id: str) -> bool:
        """
        开始执行步骤
        
        Args:
            step_id: 步骤 ID
        
        Returns:
            是否更新成功
        """
        try:
            heartbeat = self.load()
            if not heartbeat:
                return False
            
            heartbeat["status"] = "executing"
            heartbeat["current_step"] = step_id
            
            # 记录已开始的步骤
            started_steps = heartbeat.get("started_steps", [])
            if step_id not in started_steps:
                started_steps.append(step_id)
            heartbeat["started_steps"] = started_steps
            
            return self.save(heartbeat)
            
        except Exception as e:
            logger.error(f"{Fore.RED}[心跳状态] 开始步骤失败: {e}{Style.RESET_ALL}")
            return False
    
    def complete_step(self, step_id: str) -> bool:
        """
        完成步骤
        
        Args:
            step_id: 步骤 ID
        
        Returns:
            是否更新成功
        """
        try:
            heartbeat = self.load()
            if not heartbeat:
                return False
            
            completed_steps = heartbeat.get("completed_steps", [])
            if step_id not in completed_steps:
                completed_steps.append(step_id)
            
            heartbeat["completed_steps"] = completed_steps
            heartbeat["current_step"] = None
            heartbeat["progress"] = len(completed_steps)
            
            total_steps = heartbeat.get("total_steps", 0)
            if len(completed_steps) >= total_steps:
                heartbeat["status"] = "completed"
            else:
                heartbeat["status"] = "executing"
            
            return self.save(heartbeat)
            
        except Exception as e:
            logger.error(f"{Fore.RED}[心跳状态] 完成步骤失败: {e}{Style.RESET_ALL}")
            return False
    
    def fail_step(self, step_id: str, error_message: str) -> bool:
        """
        步骤失败
        
        Args:
            step_id: 步骤 ID
            error_message: 错误信息
        
        Returns:
            是否更新成功
        """
        try:
            heartbeat = self.load()
            if not heartbeat:
                return False
            
            heartbeat["status"] = "executing"
            heartbeat["current_step"] = None
            heartbeat["error_count"] = heartbeat.get("error_count", 0) + 1
            heartbeat["last_error"] = error_message
            
            failed_steps = heartbeat.get("failed_steps", [])
            if step_id not in failed_steps:
                failed_steps.append(step_id)
            heartbeat["failed_steps"] = failed_steps
            
            return self.save(heartbeat)
            
        except Exception as e:
            logger.error(f"{Fore.RED}[心跳状态] 步骤失败处理失败: {e}{Style.RESET_ALL}")
            return False
    
    def update_status(self, status: str) -> bool:
        """
        更新任务状态
        
        Args:
            status: 新状态（pending/executing/completed/failed/abandoned）
        
        Returns:
            是否更新成功
        """
        try:
            heartbeat = self.load()
            if not heartbeat:
                return False
            
            heartbeat["status"] = status
            
            return self.save(heartbeat)
            
        except Exception as e:
            logger.error(f"{Fore.RED}[心跳状态] 更新状态失败: {e}{Style.RESET_ALL}")
            return False
    
    def get_progress(self) -> Dict:
        """
        获取任务进度
        
        Returns:
            进度字典，包含 completed, total, percent
        """
        heartbeat = self.load()
        if not heartbeat:
            return {"completed": 0, "total": 0, "percent": 0}
        
        completed = len(heartbeat.get("completed_steps", []))
        total = heartbeat.get("total_steps", 0)
        percent = int((completed / total) * 100) if total > 0 else 0
        
        return {
            "completed": completed,
            "total": total,
            "percent": percent
        }
    
    def get_current_step(self) -> Optional[str]:
        """
        获取当前步骤 ID
        
        Returns:
            当前步骤 ID，无则返回 None
        """
        heartbeat = self.load()
        if not heartbeat:
            return None
        
        return heartbeat.get("current_step")
    
    def get_completed_steps(self) -> List[str]:
        """
        获取已完成步骤列表
        
        Returns:
            已完成步骤 ID 列表
        """
        heartbeat = self.load()
        if not heartbeat:
            return []
        
        return heartbeat.get("completed_steps", [])
    
    def has_pending_task(self) -> Optional[Dict]:
        """
        检查是否有未完成任务
        
        Returns:
            未完成任务信息字典，无则返回 None
        """
        heartbeat = self.load()
        
        if not heartbeat:
            return None
        
        status = heartbeat.get("status", "")
        if status not in ["pending", "executing"]:
            return None
        
        return {
            "task_id": heartbeat.get("task_id"),
            "progress": f"{len(heartbeat.get('completed_steps', []))}/{heartbeat.get('total_steps', 0)}",
            "current_step": heartbeat.get("current_step"),
            "status": status,
            "updated_at": heartbeat.get("updated_at", "")
        }
    
    def get_task_id(self) -> Optional[str]:
        """
        获取当前任务 ID
        
        Returns:
            当前任务 ID，无则返回 None
        """
        heartbeat = self.load()
        if not heartbeat:
            return None
        return heartbeat.get("task_id")
    
    def reset(self) -> bool:
        """
        重置心跳状态（用于重试）
        
        Returns:
            是否重置成功
        """
        try:
            heartbeat = self.load()
            if not heartbeat:
                return False
            
            heartbeat["status"] = "pending"
            heartbeat["current_step"] = None
            heartbeat["error_count"] = 0
            heartbeat["last_error"] = None
            
            return self.save(heartbeat)
            
        except Exception as e:
            logger.error(f"{Fore.RED}[心跳状态] 重置心跳失败: {e}{Style.RESET_ALL}")
            return False
    
    def clear(self) -> bool:
        """
        清除心跳文件（任务完成或放弃时调用）
        
        Returns:
            是否清除成功
        """
        try:
            if self.heartbeat_file.exists():
                self.heartbeat_file.unlink()
                logger.info(f"{Fore.GREEN}[心跳状态] 心跳已清除{Style.RESET_ALL}")
            return True
            
        except Exception as e:
            logger.error(f"{Fore.RED}[心跳状态] 清除心跳失败: {e}{Style.RESET_ALL}")
            return False
    
    def increment_error(self, error_message: str) -> bool:
        """
        增加错误计数
        
        Args:
            error_message: 错误信息
        
        Returns:
            是否更新成功
        """
        try:
            heartbeat = self.load()
            if not heartbeat:
                return False
            
            heartbeat["error_count"] = heartbeat.get("error_count", 0) + 1
            heartbeat["last_error"] = error_message
            
            return self.save(heartbeat)
            
        except Exception as e:
            logger.error(f"{Fore.RED}[心跳状态] 增加错误计数失败: {e}{Style.RESET_ALL}")
            return False
