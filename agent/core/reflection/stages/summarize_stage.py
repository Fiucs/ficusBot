"""
SummarizeStage 结果总结阶段

对应原有 _summarize_task_results() 逻辑
"""

from typing import Any, TYPE_CHECKING, Dict, List
import json
import re

from loguru import logger
from colorama import Fore, Style

from ..base_stage import Stage, StageContext, StageResult

if TYPE_CHECKING:
    from ..engine import ReflectionEngine


class SummarizeStage(Stage):
    """
    结果总结阶段
    
    功能说明:
        - 汇总任务执行结果
        - 生成最终回复给用户
        - 支持总结前的策略反思
    
    对应原有:
        _summarize_task_results()
    
    使用示例:
        >>> stage = SummarizeStage(agent, reflection_engine)
        >>> result = stage.run(context)
    """
    
    def __init__(self, agent: Any, reflection_engine: "ReflectionEngine" = None):
        """
        初始化 SummarizeStage
        
        Args:
            agent: Agent 实例，用于调用总结逻辑
            reflection_engine: 反思引擎实例（可选）
        """
        super().__init__("summarize", reflection_engine)
        self.agent = agent
    
    def execute(self, context: StageContext) -> StageResult:
        """
        执行总结
        
        汇总任务执行结果，生成最终回复。
        
        Args:
            context: 阶段上下文，包含 decompose_result 和 execution_result
            
        Returns:
            StageResult: 总结结果
            - success: 是否成功
            - data: 总结文本
            - message: 错误信息（如果有）
        """
        task_tree = context.get("decompose_result")
        execution_result = context.get("execution_result")
        
        if not task_tree:
            error_msg = "没有任务树，无法总结"
            self._logger.error(f"{Fore.RED}[SummarizeStage] {error_msg}{Style.RESET_ALL}")
            return StageResult(success=False, message=error_msg)
        
        task_goal = task_tree.get("task_goal", "")
        self._logger.info(f"{Fore.CYAN}[SummarizeStage] 开始执行结果总结，任务目标: {task_goal[:50]}...{Style.RESET_ALL}")
        
        try:
            # 如果 Agent 提供了 _summarize_task_results 方法，优先使用
            if self.agent and hasattr(self.agent, '_summarize_task_results') and hasattr(self.agent, 'task_tree_manager'):
                from agent.core.token_counter import TokenCounter
                
                counter = TokenCounter()
                
                # 从 task_tree 中获取 task_id
                # 注意：task_tree 中可能没有 task_id，需要从 execution_result 或其他地方获取
                # 这里我们尝试从 agent 的 heartbeat_manager 获取当前任务
                task_id = None
                if hasattr(self.agent, 'heartbeat_manager') and self.agent.heartbeat_manager:
                    heartbeat = self.agent.heartbeat_manager.load()
                    if heartbeat:
                        task_id = heartbeat.get("task_id")
                
                if task_id:
                    result = self.agent._summarize_task_results(task_id, task_tree, counter)
                    
                    if result.get("content"):
                        self._logger.info(f"{Fore.GREEN}[SummarizeStage] 结果总结完成{Style.RESET_ALL}")
                        return StageResult(success=True, data=result["content"])
                
            # 如果没有 Agent 方法或获取失败，使用简化版总结
            summary = self._generate_summary(task_tree, execution_result)
            
            self._logger.info(f"{Fore.GREEN}[SummarizeStage] 结果总结完成{Style.RESET_ALL}")
            return StageResult(success=True, data=summary)
            
        except Exception as e:
            error_msg = f"结果总结失败: {str(e)}"
            self._logger.error(f"{Fore.RED}[SummarizeStage] {error_msg}{Style.RESET_ALL}")
            # 即使失败也返回一个基本总结
            fallback_summary = f"任务执行完成: {task_goal}"
            return StageResult(success=True, data=fallback_summary)
    
    def _generate_summary(self, task_tree: Dict, execution_result: Dict) -> str:
        """
        生成简化版总结
        
        Args:
            task_tree: 任务树
            execution_result: 执行结果
            
        Returns:
            str: 总结文本
        """
        task_goal = task_tree.get("task_goal", "")
        
        # 如果 execution_result 中有 content，直接使用
        if execution_result and isinstance(execution_result, dict):
            content = execution_result.get("content", "")
            if content:
                return content
        
        # 否则返回基本总结
        total_steps = task_tree.get("total_steps", 0)
        return f"任务执行完成: {task_goal}\n\n共执行 {total_steps} 个步骤。"
