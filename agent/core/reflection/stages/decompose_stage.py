"""
DecomposeStage 任务拆解阶段

对应原有 TaskDecomposer.analyze_and_decompose() 逻辑
"""

from typing import Any, TYPE_CHECKING, List, Dict, Optional

from loguru import logger
from colorama import Fore, Style

from ..base_stage import Stage, StageContext, StageResult

if TYPE_CHECKING:
    from ..engine import ReflectionEngine


class DecomposeStage(Stage):
    """
    任务拆解阶段
    
    功能说明:
        - 分析用户输入的意图
        - 将复杂任务拆解为可执行的子任务树
    
    对应原有:
        TaskDecomposer.analyze_and_decompose()
    
    使用示例:
        >>> stage = DecomposeStage(task_decomposer, reflection_engine)
        >>> result = stage.run(StageContext(user_input="查询天气并发送邮件"))
    """
    
    def __init__(self, task_decomposer: Any, reflection_engine: "ReflectionEngine" = None):
        """
        初始化 DecomposeStage
        
        Args:
            task_decomposer: 任务拆解器实例
            reflection_engine: 反思引擎实例（可选）
        """
        super().__init__("decompose", reflection_engine)
        self.task_decomposer = task_decomposer
    
    def execute(self, context: StageContext) -> StageResult:
        """
        执行任务拆解
        
        分析用户输入，拆解为任务树。
        
        Args:
            context: 阶段上下文，包含 user_input
            
        Returns:
            StageResult: 拆解结果
            - success: 是否成功
            - data: 任务树
            - message: 错误信息（如果有）
        """
        user_input = context.user_input
        
        if not user_input:
            error_msg = "用户输入为空，无法拆解任务"
            self._logger.error(error_msg)
            return StageResult(success=False, message=error_msg)
        
        self._logger.info(f"{Fore.CYAN}[DecomposeStage] 开始任务拆解: {user_input[:50]}...{Style.RESET_ALL}")
        
        try:
            # 从上下文中获取可选参数
            ability_tags = context.get("ability_tags", [])
            pending_task = context.get("pending_task")
            
            # 如果没有提供 ability_tags，使用默认值
            if not ability_tags:
                ability_tags = ["llm_response", "文件读取", "文件写入", "命令执行", "网络搜索"]
                self._logger.debug(f"使用默认能力标签: {ability_tags}")
            
            # 调用真实的任务拆解器
            if self.task_decomposer:
                task_tree = self.task_decomposer.analyze_and_decompose(
                    user_task=user_input,
                    ability_tags=ability_tags,
                    pending_task=pending_task
                )
                
                # 保存 token 使用量到上下文
                context.set("decompose_prompt_tokens", task_tree.get("prompt_tokens", 0))
                context.set("decompose_completion_tokens", task_tree.get("completion_tokens", 0))
                
                self._logger.info(f"{Fore.GREEN}[DecomposeStage] 任务拆解完成，类型: {task_tree.get('task_type')}, 步骤数: {task_tree.get('total_steps', 0)}{Style.RESET_ALL}")
                
                return StageResult(success=True, data=task_tree)
            else:
                # task_decomposer 未提供，返回模拟数据（用于测试）
                self._logger.warning(f"{Fore.YELLOW}[DecomposeStage] task_decomposer 未提供，返回模拟数据{Style.RESET_ALL}")
                mock_task_tree = {
                    "task_type": "new_task",
                    "task_goal": user_input,
                    "total_steps": 1,
                    "task_tree": [
                        {
                            "step_id": "step_1",
                            "step_desc": user_input,
                            "required_abilities": ["llm_response"],
                            "dependencies": []
                        }
                    ],
                    "prompt_tokens": 0,
                    "completion_tokens": 0
                }
                return StageResult(success=True, data=mock_task_tree)
            
        except Exception as e:
            error_msg = f"任务拆解失败: {str(e)}"
            self._logger.error(f"{Fore.RED}[DecomposeStage] {error_msg}{Style.RESET_ALL}")
            return StageResult(success=False, message=error_msg)
