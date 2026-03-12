"""
StagePipeline 执行器模块

提供阶段管道的执行功能，串联多个 Stage 顺序执行。
"""

from typing import List, Optional
from loguru import logger

from .base_stage import Stage, StageContext, StageResult


class StagePipeline:
    """
    阶段管道执行器
    
    功能说明:
        - 串联多个 Stage 顺序执行
        - 管理执行上下文，在 Stage 之间传递数据
        - 处理 Stage 执行异常
    
    核心方法:
        - execute: 执行整个管道
        - _update_context: 更新上下文供下一阶段使用
    
    执行流程:
        1. 遍历所有 Stage
        2. 依次执行每个 Stage 的 run() 方法
        3. 更新上下文，传递执行结果
        4. 任一 Stage 失败则终止执行
    
    使用示例:
        >>> stages = [DecomposeStage(), ExecutionStage(), SummarizeStage()]
        >>> pipeline = StagePipeline(stages)
        >>> result = pipeline.execute(StageContext(user_input="查询天气"))
    """
    
    def __init__(self, stages: List[Stage]):
        """
        初始化 StagePipeline
        
        Args:
            stages: Stage 列表，按执行顺序排列
        """
        self.stages = stages
        self._logger = logger.bind(component="StagePipeline")
    
    def execute(self, initial_context: StageContext) -> StageResult:
        """
        执行整个管道
        
        按顺序执行所有 Stage，任一 Stage 失败则终止。
        每执行完一个 Stage，会更新上下文供下一阶段使用。
        
        Args:
            initial_context: 初始上下文，包含用户输入
            
        Returns:
            StageResult: 最终执行结果
            - 成功: 包含所有阶段执行后的数据
            - 失败: 包含错误信息
            
        示例:
            >>> context = StageContext(user_input="查询天气")
            >>> result = pipeline.execute(context)
            >>> if result.success:
            ...     print(result.data)
            ... else:
            ...     print(f"执行失败: {result.message}")
        """
        self._logger.info(f"Pipeline 开始执行，共 {len(self.stages)} 个阶段")
        context = initial_context
        
        for index, stage in enumerate(self.stages, 1):
            try:
                self._logger.info(f"[{index}/{len(self.stages)}] 执行阶段: {stage.name}")
                
                # 执行 Stage
                result = stage.run(context)
                
                # 检查执行结果
                if not result.success:
                    self._logger.warning(f"阶段 {stage.name} 执行失败: {result.message}")
                    return StageResult(
                        success=False,
                        message=f"阶段 {stage.name} 执行失败: {result.message}"
                    )
                
                # 更新上下文供下一阶段使用
                context = self._update_context(context, stage.name, result)
                self._logger.info(f"阶段 {stage.name} 执行成功")
                
            except Exception as e:
                error_msg = f"阶段 {stage.name} 执行异常: {str(e)}"
                self._logger.error(error_msg)
                return StageResult(success=False, message=error_msg)
        
        self._logger.info("Pipeline 执行完成")
        return StageResult(success=True, data=context.data)
    
    def _update_context(self, context: StageContext, stage_name: str, result: StageResult) -> StageContext:
        """
        更新上下文
        
        将当前 Stage 的执行结果保存到上下文中，
        供后续 Stage 使用。
        
        Args:
            context: 当前上下文
            stage_name: 阶段名称
            result: 阶段执行结果
            
        Returns:
            StageContext: 更新后的上下文
        """
        result_key = f"{stage_name}_result"
        context.set(result_key, result.data)
        
        self._logger.debug(f"更新上下文: {result_key} = {result.data}")
        return context
    
    def add_stage(self, stage: Stage, index: Optional[int] = None):
        """
        添加 Stage
        
        Args:
            stage: 要添加的 Stage
            index: 插入位置（可选，默认添加到末尾）
        """
        if index is None:
            self.stages.append(stage)
        else:
            self.stages.insert(index, stage)
        
        self._logger.info(f"添加阶段 {stage.name}，当前共 {len(self.stages)} 个阶段")
    
    def remove_stage(self, stage_name: str) -> bool:
        """
        移除指定名称的 Stage
        
        Args:
            stage_name: 阶段名称
            
        Returns:
            bool: 是否成功移除
        """
        for i, stage in enumerate(self.stages):
            if stage.name == stage_name:
                self.stages.pop(i)
                self._logger.info(f"移除阶段 {stage_name}")
                return True
        
        self._logger.warning(f"未找到阶段 {stage_name}")
        return False
    
    def __repr__(self) -> str:
        """返回 Pipeline 的字符串表示"""
        stage_names = [s.name for s in self.stages]
        return f"StagePipeline(stages={stage_names})"
