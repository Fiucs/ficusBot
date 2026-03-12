"""
Stage 基类模块

提供阶段执行的抽象基类，定义标准执行流程和反思钩子。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from .engine import ReflectionEngine


@dataclass
class StageContext:
    """
    阶段上下文数据类
    
    功能说明:
        - 在 Stage 之间传递数据
        - 保存用户输入和执行过程中的中间结果
    
    属性:
        user_input: 用户原始输入
        data: 存储各阶段的执行结果和其他数据
    
    使用示例:
        >>> context = StageContext(user_input="查询天气")
        >>> context.data["decompose_result"] = task_tree
    """
    
    user_input: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """确保 data 是字典类型"""
        if self.data is None:
            self.data = {}
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        从 data 中获取值
        
        Args:
            key: 键名
            default: 默认值
            
        Returns:
            键对应的值或默认值
        """
        return self.data.get(key, default)
    
    def set(self, key: str, value: Any):
        """
        向 data 中设置值
        
        Args:
            key: 键名
            value: 值
        """
        self.data[key] = value


@dataclass
class StageResult:
    """
    阶段执行结果数据类
    
    功能说明:
        - 封装阶段的执行结果
        - 包含成功状态、数据和错误信息
    
    属性:
        success: 是否执行成功
        data: 执行结果数据
        message: 附加信息（通常是错误信息）
    
    使用示例:
        >>> result = StageResult(success=True, data=task_tree)
        >>> result = StageResult(success=False, message="拆解失败")
    """
    
    success: bool = True
    data: Any = None
    message: str = ""


@dataclass
class ReflectionDecision:
    """
    反思决策结果数据类
    
    功能说明:
        - 封装反思引擎的决策结果
        - 指示是否需要调整、重试以及调整后的上下文
    
    属性:
        should_adjust: 是否需要调整上下文
        should_retry: 是否需要重试执行
        adjusted_context: 调整后的上下文（如果需要）
        reason: 决策理由
    
    使用示例:
        >>> decision = ReflectionDecision(should_adjust=True, adjusted_context=new_context)
        >>> decision = ReflectionDecision(should_retry=True, reason="执行失败，需要重试")
    """
    
    should_adjust: bool = False
    should_retry: bool = False
    adjusted_context: Optional[StageContext] = None
    reason: str = ""


class Stage(ABC):
    """
    阶段基类
    
    功能说明:
        - 定义标准的阶段执行流程（模板方法模式）
        - 提供前置反思和后置反思的钩子
        - 子类只需实现 execute() 方法即可
    
    核心方法:
        - run: 标准执行流程（模板方法，子类不重写）
        - execute: 业务逻辑（子类必须实现）
    
    执行流程:
        1. 前置反思（如果启用）
        2. 执行业务逻辑
        3. 后置反思（如果启用且执行失败）
    
    使用示例:
        >>> class MyStage(Stage):
        ...     def execute(self, context: StageContext) -> StageResult:
        ...         # 实现业务逻辑
        ...         return StageResult(success=True, data=result)
    """
    
    def __init__(self, name: str, reflection_engine: Optional["ReflectionEngine"] = None):
        """
        初始化 Stage
        
        Args:
            name: 阶段名称
            reflection_engine: 反思引擎实例（可选）
        """
        self.name = name
        self.reflection_engine = reflection_engine
        self._logger = logger.bind(stage=name)
    
    def run(self, context: StageContext) -> StageResult:
        """
        执行阶段（模板方法）
        
        执行流程:
            1. 前置反思：调用 reflection_engine.reflect_before()
            2. 业务执行：调用子类实现的 execute()
            3. 后置反思：如果执行失败，调用 reflection_engine.reflect_after()
        
        Args:
            context: 阶段上下文
            
        Returns:
            StageResult: 阶段执行结果
        """
        self._logger.info(f"[{self.name}] 阶段开始执行")
        
        # 1. 前置反思
        if self.reflection_engine:
            decision = self.reflection_engine.reflect_before(self.name, context)
            if decision.should_adjust and decision.adjusted_context:
                context = decision.adjusted_context
                self._logger.info(f"[{self.name}] 前置反思调整上下文: {decision.reason}")
        
        # 2. 执行核心业务
        result = self.execute(context)
        
        # 3. 后置反思（仅在执行失败时触发）
        if self.reflection_engine and not result.success:
            decision = self.reflection_engine.reflect_after(self.name, context, result)
            if decision.should_retry:
                self._logger.info(f"[{self.name}] 后置反思触发重试: {decision.reason}")
                result = self.execute(context)
        
        self._logger.info(f"[{self.name}] 阶段执行完成，成功={result.success}")
        return result
    
    @abstractmethod
    def execute(self, context: StageContext) -> StageResult:
        """
        执行阶段业务逻辑（子类必须实现）
        
        Args:
            context: 阶段上下文，包含用户输入和之前阶段的结果
            
        Returns:
            StageResult: 阶段执行结果
            
        示例:
            >>> def execute(self, context: StageContext) -> StageResult:
            ...     try:
            ...         result = self.do_something(context.user_input)
            ...         return StageResult(success=True, data=result)
            ...     except Exception as e:
            ...         return StageResult(success=False, message=str(e))
        """
        pass
    
    def __repr__(self) -> str:
        """返回 Stage 的字符串表示"""
        return f"Stage(name='{self.name}', reflection_enabled={self.reflection_engine is not None})"
