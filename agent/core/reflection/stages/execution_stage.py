"""
ExecutionStage 任务执行阶段

对应原有 _execute_task_with_tree() 逻辑
支持执行前多轮反思，控制思考深度
"""

from typing import Any, TYPE_CHECKING, Dict, List


from loguru import logger
from colorama import Fore, Style

from ..base_stage import Stage, StageContext, StageResult

if TYPE_CHECKING:
    from ..engine import ReflectionEngine
    from agent.core.agent import Agent


class ExecutionStage(Stage):
    """
    任务执行阶段
    
    功能说明:
        - 执行任务树中的各个步骤
        - 支持多轮前置反思，灵活控制思考深度
        - 调用工具完成具体任务
    
    对应原有:
        _execute_task_with_tree()
    
    使用示例:
        >>> stage = ExecutionStage(agent, reflection_engine)
        >>> result = stage.run(context)
    """
    
    def __init__(self, agent: "Agent", reflection_engine: "ReflectionEngine" = None):
        """
        初始化 ExecutionStage
        
        Args:
            agent: Agent 实例，用于调用执行逻辑
            reflection_engine: 反思引擎实例（可选）
        """
        super().__init__("execute", reflection_engine)
        self.agent = agent
    
    def execute(self, context: StageContext) -> StageResult:
        """
        执行任务
        
        执行流程:
            1. 获取任务树
            2. 执行前多轮反思（控制思考深度）
            3. 执行任务
        
        Args:
            context: 阶段上下文，包含 decompose_result
            
        Returns:
            StageResult: 执行结果
            - success: 是否成功
            - data: 执行结果数据
            - message: 错误信息（如果有）
        """
        task_tree = context.get("decompose_result")
        
        if not task_tree:
            error_msg = "没有任务树，无法执行"
            self._logger.error(f"{Fore.RED}[ExecutionStage] {error_msg}{Style.RESET_ALL}")
            return StageResult(success=False, message=error_msg)
        
        task_type = task_tree.get("task_type", "new_task")
        task_goal = task_tree.get("task_goal", "")
        
        self._logger.info(f"{Fore.CYAN}[ExecutionStage] 开始执行任务，类型: {task_type}, 目标: {task_goal[:50]}...{Style.RESET_ALL}")
        
        try:
            # 1. 执行前多轮反思（控制思考深度）
            if self.reflection_engine:
                context = self._multi_round_reflection(context)
            
            # 2. 调用 Agent 的真实执行逻辑
            if self.agent and hasattr(self.agent, '_execute_by_task_type'):
                from agent.core.token_counter import TokenCounter
                
                # 获取用户输入（从上下文或任务树）
                user_input = context.user_input or task_goal
                
                # 获取图片（从上下文）
                images = context.get("images")
                
                # 创建 TokenCounter 用于统计执行阶段的 token
                counter = TokenCounter()
                
                # 调用 Agent 的执行方法（Pipeline 模式，跳过汇总）
                result = self.agent._execute_by_task_type(
                    task_tree, 
                    user_input, 
                    counter, 
                    skip_summarize=True,
                    images=images
                )
                
                # 保存执行结果到上下文
                context.set("execution_result", result)
                context.set("execution_prompt_tokens", result.get("total_prompt_tokens", 0))
                context.set("execution_completion_tokens", result.get("total_completion_tokens", 0))
                context.set("execution_elapsed_time", result.get("elapsed_time", 0.0))
                
                # 保存 task_id 和 task_tree 到上下文（供 SummarizeStage 使用）
                task_id = result.get("task_id")
                if task_id:
                    context.set("task_id", task_id)
                    context.set("task_tree", task_tree)
                    context.set("final_status", result.get("final_status", "completed"))
                    self._logger.info(f"{Fore.GREEN}[ExecutionStage] 任务执行完成，task_id: {task_id}{Style.RESET_ALL}")
                    return StageResult(success=True, data=result)
                else:
                    # Legacy 模式（直接返回了汇总结果）
                    if result.get("content"):
                        self._logger.info(f"{Fore.GREEN}[ExecutionStage] 任务执行完成（Legacy 模式）{Style.RESET_ALL}")
                        return StageResult(success=True, data=result)
                    else:
                        error_msg = "任务执行返回空结果且无 task_id"
                        self._logger.warning(f"{Fore.YELLOW}[ExecutionStage] {error_msg}{Style.RESET_ALL}")
                        return StageResult(success=False, message=error_msg)
            else:
                # Agent 未提供，返回模拟数据（用于测试）
                self._logger.warning(f"{Fore.YELLOW}[ExecutionStage] Agent 未提供或缺少 _execute_by_task_type 方法，返回模拟数据{Style.RESET_ALL}")
                mock_result = {
                    "content": f"任务执行完成: {task_goal}",
                    "total_prompt_tokens": 0,
                    "total_completion_tokens": 0,
                    "elapsed_time": 0.0
                }
                context.set("execution_result", mock_result)
                return StageResult(success=True, data=mock_result)
            
        except Exception as e:
            error_msg = f"任务执行失败: {str(e)}"
            self._logger.error(f"{Fore.RED}[ExecutionStage] {error_msg}{Style.RESET_ALL}")
            return StageResult(success=False, message=error_msg)
    
    def _multi_round_reflection(self, context: StageContext) -> StageContext:
        """
        多轮前置反思
        
        支持 LLM 多次思考，直到认为不需要调整或达到最大轮数。
        这是控制思考深度的核心机制。
        
        Args:
            context: 当前上下文
            
        Returns:
            StageContext: 可能经过多轮调整后的上下文
        """
        if not self.reflection_engine:
            return context
        
        max_rounds = self.reflection_engine.config.max_rounds
        self._logger.info(f"{Fore.CYAN}[ExecutionStage] 开始多轮前置反思，最大轮数: {max_rounds}{Style.RESET_ALL}")
        
        for round_num in range(max_rounds):
            # 调用反思引擎进行前置反思
            decision = self.reflection_engine.reflect_before("execute", context)
            
            if not decision.should_adjust:
                self._logger.info(f"{Fore.CYAN}[ExecutionStage] 第 {round_num + 1} 轮反思：无需调整，结束反思{Style.RESET_ALL}")
                break
            
            if decision.adjusted_context:
                context = decision.adjusted_context
                self._logger.info(f"{Fore.CYAN}[ExecutionStage] 第 {round_num + 1} 轮反思：调整上下文 - {decision.reason}{Style.RESET_ALL}")
        else:
            # 达到最大轮数
            self._logger.info(f"{Fore.CYAN}[ExecutionStage] 达到最大反思轮数 {max_rounds}，结束反思{Style.RESET_ALL}")
        
        return context
