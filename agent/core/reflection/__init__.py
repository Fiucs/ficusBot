"""
反思机制模块

提供 Agent 的反思功能，支持在任务拆解、执行、总结阶段插入反思流程。

主要组件:
    - ReflectionConfig: 反思配置类
    - ReflectionEngine: 反思引擎
    - Stage: 阶段基类
    - StageContext: 阶段上下文
    - StageResult: 阶段结果
    - StagePipeline: 阶段管道执行器
    - DecomposeStage: 任务拆解阶段
    - ExecutionStage: 任务执行阶段
    - SummarizeStage: 结果总结阶段

使用示例:
    >>> from agent.core.reflection import (
    ...     ReflectionConfig,
    ...     ReflectionEngine,
    ...     StagePipeline,
    ...     DecomposeStage,
    ...     ExecutionStage,
    ...     SummarizeStage,
    ... )
    >>> 
    >>> # 创建配置
    >>> config = ReflectionConfig(enabled=True, max_rounds=2)
    >>> 
    >>> # 创建反思引擎
    >>> engine = ReflectionEngine(llm_client, config)
    >>> 
    >>> # 创建 Stage Pipeline
    >>> stages = [
    ...     DecomposeStage(task_decomposer, engine),
    ...     ExecutionStage(agent, engine),
    ...     SummarizeStage(agent, engine),
    ... ]
    >>> pipeline = StagePipeline(stages)
    >>> 
    >>> # 执行
    >>> result = pipeline.execute(StageContext(user_input="查询天气"))
"""

# 配置
from .config import ReflectionConfig

# 引擎
from .engine import ReflectionEngine

# 基类
from .base_stage import Stage, StageContext, StageResult, ReflectionDecision

# 管道
from .pipeline import StagePipeline

# 具体 Stage
from .stages import DecomposeStage, ExecutionStage, SummarizeStage

__all__ = [
    # 配置
    "ReflectionConfig",
    
    # 引擎
    "ReflectionEngine",
    
    # 基类
    "Stage",
    "StageContext",
    "StageResult",
    "ReflectionDecision",
    
    # 管道
    "StagePipeline",
    
    # 具体 Stage
    "DecomposeStage",
    "ExecutionStage",
    "SummarizeStage",
]

__version__ = "1.0.0"
