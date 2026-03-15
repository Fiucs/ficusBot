"""
SummarizeStage 结果总结阶段

对应原有 _summarize_task_results() 逻辑
负责汇总任务执行结果、清理 heartbeat、更新对话历史
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
        - 从 context 获取 task_id 和 task_tree
        - 汇总任务执行结果
        - 清理 heartbeat
        - 更新对话历史
        - 生成最终回复给用户
    
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
            context: 阶段上下文，包含 task_id, task_tree, final_status
            
        Returns:
            StageResult: 总结结果
            - success: 是否成功
            - data: 总结文本
            - message: 错误信息（如果有）
        """
        # 从 context 获取 task_id（由 ExecutionStage 设置）
        task_id = context.get("task_id")
        task_tree = context.get("task_tree")
        final_status = context.get("final_status", "completed")
        
        if not task_id:
            # 没有 task_id，可能是 Legacy 模式，直接返回 execution_result 的内容
            execution_result = context.get("execution_result")
            if execution_result and execution_result.get("content"):
                self._logger.info(f"{Fore.GREEN}[SummarizeStage] Legacy 模式，直接返回执行结果{Style.RESET_ALL}")
                return StageResult(success=True, data={"summarize_result": execution_result.get("content")})
            
            error_msg = "没有 task_id，无法总结"
            self._logger.error(f"{Fore.RED}[SummarizeStage] {error_msg}{Style.RESET_ALL}")
            return StageResult(success=False, message=error_msg)
        
        if not task_tree:
            error_msg = "没有任务树，无法总结"
            self._logger.error(f"{Fore.RED}[SummarizeStage] {error_msg}{Style.RESET_ALL}")
            return StageResult(success=False, message=error_msg)
        
        task_goal = task_tree.get("task_goal", "")
        self._logger.info(f"{Fore.CYAN}[SummarizeStage] 开始执行结果总结，task_id: {task_id}, 目标: {task_goal[:50]}...{Style.RESET_ALL}")
        
        try:
            from agent.core.token_counter import TokenCounter
            
            counter = TokenCounter()
            
            # 调用 Agent 的汇总方法
            summary_result = self.agent.task_executor.summarize_task_results(task_id, task_tree, counter)
            
            # 处理部分完成的情况
            if final_status == "partial_completed":
                failed_steps = [s for s in task_tree.get("task_tree", []) if s.get("status") == "failed"]
                failed_info = "\n".join([f"- {s.get('step_id')}: {s.get('error_message', '未知错误')}" for s in failed_steps])
                summary_result["content"] = f"{summary_result.get('content', '')}\n\n⚠️ [总结]部分步骤执行失败:\n{failed_info}"
            
            if self.agent.heartbeat_manager:
                self.agent.heartbeat_manager.clear()
                self._logger.info(f"{Fore.CYAN}[SummarizeStage] 已清理 heartbeat{Style.RESET_ALL}")
            
            summary_content = summary_result.get("content", "")
            
            # 注意：不在这里添加 assistant 消息到 history
            # 因为 _chat_with_pipeline 会调用 finalize_conversation 来处理
            # 避免重复添加
            
            # 保存汇总 token 统计到上下文
            context.set("summarize_prompt_tokens", counter.total_prompt_tokens)
            context.set("summarize_completion_tokens", counter.total_completion_tokens)
            
            self._logger.info(f"{Fore.GREEN}[SummarizeStage] 结果总结完成{Style.RESET_ALL}")
            
            return StageResult(success=True, data={"summarize_result": summary_content})
            
        except Exception as e:
            error_msg = f"结果总结失败: {str(e)}"
            self._logger.error(f"{Fore.RED}[SummarizeStage] {error_msg}{Style.RESET_ALL}")
            # 即使失败也返回一个基本总结
            fallback_summary = f"任务执行完成: {task_goal}"
            return StageResult(success=True, data={"summarize_result": fallback_summary})
