#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :task_tree_manager.py
# @Time      :2026/03/10
# @Author    :Ficus

"""
任务树管理器 - 管理任务树的持久化和状态更新

核心功能:
    - 保存任务树到 JSON 文件
    - 加载任务树从 JSON 文件
    - 更新任务树状态
    - 获取可执行步骤
    - 管理任务结果存储

设计原则:
    - 任务树文件为只读参考
    - 状态变更通过方法调用
    - 支持断点续跑

使用示例:
    >>> manager = TaskTreeManager(workspace_root)
    >>> manager.save(task_id, task_tree)
    >>> task_tree = manager.load(task_id)
    >>> manager.update_step_status(task_id, "step_1", "completed")
"""

import json
import os
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

from loguru import logger
from colorama import Fore, Style


class TaskTreeManager:
    """
    任务树管理器
    
    功能说明:
        - 管理任务树的持久化存储
        - 更新任务树状态
        - 获取可执行步骤
        - 管理步骤执行结果
        - 步骤重试机制
    
    核心方法:
        - save: 保存任务树
        - load: 加载任务树
        - update_step_status: 更新步骤状态
        - get_runnable_step: 获取可执行步骤
        - save_step_result: 保存步骤执行结果
        - increment_retry: 增加重试计数
    
    配置项:
        - MAX_STEP_RETRIES: 步骤最大重试次数，默认 2
    
    文件结构:
        workspace/tasks/{task_id}/
            - task_tree.json: 任务树
            - results.json: 步骤执行结果
    """
    
    MAX_STEP_RETRIES = 2
    
    def __init__(self, workspace_root: str):
        """
        初始化任务树管理器
        
        Args:
            workspace_root: 工作区根目录
        """
        self.workspace_root = workspace_root
        self.tasks_dir = Path(workspace_root) / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"{Fore.CYAN}任务树管理器初始化完成，任务目录: {self.tasks_dir}{Style.RESET_ALL}")
    
    def _get_task_dir(self, task_id: str) -> Path:
        """
        获取任务目录路径
        
        Args:
            task_id: 任务 ID
        
        Returns:
            任务目录路径
        """
        task_dir = self.tasks_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        return task_dir
    
    def _get_task_tree_file(self, task_id: str) -> Path:
        """
        获取任务树文件路径
        
        Args:
            task_id: 任务 ID
        
        Returns:
            任务树文件路径
        """
        return self._get_task_dir(task_id) / "task_tree.json"
    
    def _get_results_file(self, task_id: str) -> Path:
        """
        获取结果文件路径
        
        Args:
            task_id: 任务 ID
        
        Returns:
            结果文件路径
        """
        return self._get_task_dir(task_id) / "results.json"
    
    def generate_task_id(self) -> str:
        """
        生成任务 ID
        
        Returns:
            任务 ID，格式为 task_YYYYMMDD_HHMMSS
        """
        return f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    def save(self, task_id: str, task_tree: Dict) -> bool:
        """
        保存任务树
        
        Args:
            task_id: 任务 ID
            task_tree: 任务树字典
        
        Returns:
            是否保存成功
        """
        try:
            task_tree_file = self._get_task_tree_file(task_id)
            
            now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            
            full_task_tree = {
                "task_id": task_id,
                "task_type": task_tree.get("task_type", "task"),
                "task_goal": task_tree.get("task_goal", ""),
                "total_steps": task_tree.get("total_steps", 0),
                "created_at": now,
                "updated_at": now,
                "status": "pending",
                "task_tree": task_tree.get("task_tree", [])
            }
            
            with open(task_tree_file, "w", encoding="utf-8") as f:
                json.dump(full_task_tree, f, ensure_ascii=False, indent=2)
            
            self._init_results_file(task_id)
            
            logger.debug(f"{Fore.GREEN}[任务树管理] 任务树已保存: {task_id}{Style.RESET_ALL}")
            return True
            
        except Exception as e:
            logger.error(f"{Fore.RED}[任务树管理] 保存任务树失败: {e}{Style.RESET_ALL}")
            return False
    
    def load(self, task_id: str) -> Optional[Dict]:
        """
        加载任务树
        
        Args:
            task_id: 任务 ID
        
        Returns:
            任务树字典，不存在则返回 None
        """
        try:
            task_tree_file = self._get_task_tree_file(task_id)
            
            if not task_tree_file.exists():
                logger.warning(f"{Fore.YELLOW}[任务树管理] 任务树文件不存在: {task_id}{Style.RESET_ALL}")
                return None
            
            with open(task_tree_file, "r", encoding="utf-8") as f:
                task_tree = json.load(f)
            
            logger.debug(f"{Fore.GREEN}[任务树管理] 任务树已加载: {task_id}{Style.RESET_ALL}")
            return task_tree
            
        except Exception as e:
            logger.error(f"{Fore.RED}[任务树管理] 加载任务树失败: {e}{Style.RESET_ALL}")
            return None
    
    def update_step_status(
        self, 
        task_id: str, 
        step_id: str, 
        status: str,
        error_message: Optional[str] = None
    ) -> bool:
        """
        更新步骤状态
        
        Args:
            task_id: 任务 ID
            step_id: 步骤 ID
            status: 新状态（pending/executing/completed/failed）
            error_message: 错误信息（可选）
        
        Returns:
            是否更新成功
        """
        try:
            task_tree = self.load(task_id)
            if not task_tree:
                return False
            
            now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            
            for step in task_tree.get("task_tree", []):
                if step["step_id"] == step_id:
                    step["status"] = status
                    
                    if status == "executing":
                        step["started_at"] = now
                    elif status in ["completed", "failed"]:
                        step["completed_at"] = now
                        if error_message:
                            step["error_message"] = error_message
                    
                    if status == "failed":
                        retry_count = step.get("retry_count", 0)
                        if retry_count >= self.MAX_STEP_RETRIES:
                            self._mark_dependents_failed(task_tree, step_id)
                    break
            
            task_tree["updated_at"] = now
            
            all_completed = all(
                step["status"] == "completed" 
                for step in task_tree.get("task_tree", [])
            )
            all_done = all(
                step["status"] in ["completed", "failed"] 
                for step in task_tree.get("task_tree", [])
            )
            
            if all_completed:
                task_tree["status"] = "completed"
            elif all_done:
                task_tree["status"] = "partial_completed"
            else:
                task_tree["status"] = "executing"
            
            task_tree_file = self._get_task_tree_file(task_id)
            with open(task_tree_file, "w", encoding="utf-8") as f:
                json.dump(task_tree, f, ensure_ascii=False, indent=2)
            
            logger.info(f"{Fore.GREEN}[任务树管理] 步骤状态已更新: {step_id} -> {status}{Style.RESET_ALL}")
            return True
            
        except Exception as e:
            logger.error(f"{Fore.RED}[任务树管理] 更新步骤状态失败: {e}{Style.RESET_ALL}")
            return False
    
    def _mark_dependents_failed(self, task_tree: Dict, failed_step_id: str):
        """
        标记依赖失败步骤的所有后续步骤为失败
        
        Args:
            task_tree: 任务树字典
            failed_step_id: 失败的步骤 ID
        """
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        
        for step in task_tree.get("task_tree", []):
            if step.get("dependent_on") == failed_step_id and step["status"] == "pending":
                step["status"] = "failed"
                step["completed_at"] = now
                step["error_message"] = f"依赖步骤 {failed_step_id} 执行失败"
                logger.warning(f"{Fore.YELLOW}[任务树管理] 步骤 {step['step_id']} 因依赖失败而标记为失败{Style.RESET_ALL}")
    
    def update_task_status(self, task_id: str, status: str) -> bool:
        """
        更新任务状态
        
        Args:
            task_id: 任务 ID
            status: 新状态（pending/executing/completed/failed/abandoned）
        
        Returns:
            是否更新成功
        """
        try:
            task_tree = self.load(task_id)
            if not task_tree:
                return False
            
            now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            task_tree["status"] = status
            task_tree["updated_at"] = now
            
            task_tree_file = self._get_task_tree_file(task_id)
            with open(task_tree_file, "w", encoding="utf-8") as f:
                json.dump(task_tree, f, ensure_ascii=False, indent=2)
            
            logger.info(f"{Fore.GREEN}[任务树管理] 任务状态已更新: {task_id} -> {status}{Style.RESET_ALL}")
            return True
            
        except Exception as e:
            logger.error(f"{Fore.RED}[任务树管理] 更新任务状态失败: {e}{Style.RESET_ALL}")
            return False
    
    def get_runnable_step(self, task_id: str, completed_steps: List[str]) -> Optional[Dict]:
        """
        获取可执行步骤
        
        根据依赖关系和已完成步骤，返回下一个可执行的步骤。
        会检查重试次数，超过最大重试次数的步骤不再返回。
        
        Args:
            task_id: 任务 ID
            completed_steps: 已完成步骤 ID 列表
        
        Returns:
            可执行步骤字典，无则返回 None
        """
        try:
            task_tree = self.load(task_id)
            if not task_tree:
                return None
            
            completed_set = set(completed_steps)
            
            for step in task_tree.get("task_tree", []):
                if step["step_id"] in completed_set:
                    continue
                
                if step["status"] not in ["pending", "failed"]:
                    continue
                
                retry_count = step.get("retry_count", 0)
                if retry_count >= self.MAX_STEP_RETRIES:
                    continue
                
                dep = step.get("dependent_on")
                if dep is None or dep in completed_set:
                    logger.debug(f"{Fore.CYAN}[任务树管理] 获取可执行步骤: {step['step_id']} (状态: {step['status']}, 重试: {retry_count}/{self.MAX_STEP_RETRIES}){Style.RESET_ALL}")
                    return step
            
            logger.info(f"{Fore.CYAN}[任务树管理] 无可执行步骤{Style.RESET_ALL}")
            return None
            
        except Exception as e:
            logger.error(f"{Fore.RED}[任务树管理] 获取可执行步骤失败: {e}{Style.RESET_ALL}")
            return None
    
    def increment_retry(self, task_id: str, step_id: str) -> int:
        """
        增加步骤的重试计数
        
        Args:
            task_id: 任务 ID
            step_id: 步骤 ID
        
        Returns:
            更新后的重试次数，失败返回 -1
        """
        try:
            task_tree = self.load(task_id)
            if not task_tree:
                return -1
            
            for step in task_tree.get("task_tree", []):
                if step["step_id"] == step_id:
                    retry_count = step.get("retry_count", 0) + 1
                    step["retry_count"] = retry_count
                    
                    task_tree_file = self._get_task_tree_file(task_id)
                    with open(task_tree_file, "w", encoding="utf-8") as f:
                        json.dump(task_tree, f, ensure_ascii=False, indent=2)
                    
                    logger.info(f"{Fore.YELLOW}[任务树管理] 步骤 {step_id} 重试计数: {retry_count}/{self.MAX_STEP_RETRIES}{Style.RESET_ALL}")
                    return retry_count
            
            return -1
            
        except Exception as e:
            logger.error(f"{Fore.RED}[任务树管理] 增加重试计数失败: {e}{Style.RESET_ALL}")
            return -1
    
    def get_current_step(self, task_id: str, heartbeat: Dict) -> Optional[Dict]:
        """
        获取当前步骤
        
        根据心跳状态获取当前正在执行或下一个可执行的步骤。
        
        Args:
            task_id: 任务 ID
            heartbeat: 心跳状态字典
        
        Returns:
            当前步骤字典，无则返回 None
        """
        completed_steps = heartbeat.get("completed_steps", [])
        return self.get_runnable_step(task_id, completed_steps)
    
    def _init_results_file(self, task_id: str):
        """
        初始化结果文件
        
        Args:
            task_id: 任务 ID
        """
        results_file = self._get_results_file(task_id)
        
        initial_results = {
            "task_id": task_id,
            "results": []
        }
        
        with open(results_file, "w", encoding="utf-8") as f:
            json.dump(initial_results, f, ensure_ascii=False, indent=2)
    
    def save_step_result(
        self, 
        task_id: str, 
        step_id: str, 
        tool_name: str,
        arguments: Dict,
        result: Dict,
        duration_ms: int = 0
    ) -> bool:
        """
        保存步骤执行结果
        
        Args:
            task_id: 任务 ID
            step_id: 步骤 ID
            tool_name: 工具名称
            arguments: 工具参数
            result: 执行结果
            duration_ms: 执行耗时（毫秒）
        
        Returns:
            是否保存成功
        """
        try:
            results_file = self._get_results_file(task_id)
            
            if results_file.exists():
                with open(results_file, "r", encoding="utf-8") as f:
                    results_data = json.load(f)
            else:
                results_data = {"task_id": task_id, "results": []}
            
            step_result = {
                "step_id": step_id,
                "tool_name": tool_name,
                "arguments": arguments,
                "result": result,
                "executed_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "duration_ms": duration_ms
            }
            
            results_data["results"].append(step_result)
            
            with open(results_file, "w", encoding="utf-8") as f:
                json.dump(results_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"{Fore.GREEN}[任务树管理] 步骤结果已保存: {step_id}{Style.RESET_ALL}")
            return True
            
        except Exception as e:
            logger.error(f"{Fore.RED}[任务树管理] 保存步骤结果失败: {e}{Style.RESET_ALL}")
            return False
    
    def load_results(self, task_id: str) -> Optional[Dict]:
        """
        加载步骤执行结果
        
        Args:
            task_id: 任务 ID
        
        Returns:
            结果字典，不存在则返回 None
        """
        try:
            results_file = self._get_results_file(task_id)
            
            if not results_file.exists():
                return None
            
            with open(results_file, "r", encoding="utf-8") as f:
                return json.load(f)
                
        except Exception as e:
            logger.error(f"{Fore.RED}[任务树管理] 加载步骤结果失败: {e}{Style.RESET_ALL}")
            return None
    
    def get_step_result(self, task_id: str, step_id: str) -> Optional[Dict]:
        """
        获取指定步骤的执行结果
        
        Args:
            task_id: 任务 ID
            step_id: 步骤 ID
        
        Returns:
            步骤结果字典，不存在则返回 None
        """
        results_data = self.load_results(task_id)
        if not results_data:
            return None
        
        for result in results_data.get("results", []):
            if result["step_id"] == step_id:
                return result
        
        return None
    
    def get_all_tasks(self) -> List[Dict]:
        """
        获取所有任务列表
        
        Returns:
            任务列表，每个任务包含 task_id, task_goal, status, created_at
        """
        tasks = []
        
        try:
            for task_dir in self.tasks_dir.iterdir():
                if task_dir.is_dir():
                    task_tree_file = task_dir / "task_tree.json"
                    if task_tree_file.exists():
                        with open(task_tree_file, "r", encoding="utf-8") as f:
                            task_tree = json.load(f)
                            tasks.append({
                                "task_id": task_tree.get("task_id", task_dir.name),
                                "task_goal": task_tree.get("task_goal", ""),
                                "status": task_tree.get("status", "unknown"),
                                "created_at": task_tree.get("created_at", ""),
                                "total_steps": task_tree.get("total_steps", 0)
                            })
        except Exception as e:
            logger.error(f"{Fore.RED}[任务树管理] 获取任务列表失败: {e}{Style.RESET_ALL}")
        
        tasks.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return tasks
    
    def delete_task(self, task_id: str) -> bool:
        """
        删除任务
        
        Args:
            task_id: 任务 ID
        
        Returns:
            是否删除成功
        """
        try:
            import shutil
            task_dir = self._get_task_dir(task_id)
            
            if task_dir.exists():
                shutil.rmtree(task_dir)
                logger.info(f"{Fore.GREEN}[任务树管理] 任务已删除: {task_id}{Style.RESET_ALL}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"{Fore.RED}[任务树管理] 删除任务失败: {e}{Style.RESET_ALL}")
            return False
    
    def archive_task(self, task_id: str) -> bool:
        """
        归档任务（移动到 archive 目录）
        
        Args:
            task_id: 任务 ID
        
        Returns:
            是否归档成功
        """
        try:
            import shutil
            task_dir = self._get_task_dir(task_id)
            archive_dir = self.tasks_dir / "archive"
            archive_dir.mkdir(parents=True, exist_ok=True)
            
            if task_dir.exists():
                archive_path = archive_dir / task_id
                if archive_path.exists():
                    shutil.rmtree(archive_path)
                shutil.move(str(task_dir), str(archive_path))
                logger.info(f"{Fore.GREEN}[任务树管理] 任务已归档: {task_id}{Style.RESET_ALL}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"{Fore.RED}[任务树管理] 归档任务失败: {e}{Style.RESET_ALL}")
            return False
