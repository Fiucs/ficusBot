"""
反思机制配置模块

提供反思功能的配置类，支持全局和各阶段的细粒度控制。
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Any


@dataclass
class ReflectionConfig:
    """
    反思配置类
    
    功能说明:
        - 控制反思机制的全局开关和各阶段行为
        - 支持拆解、执行、总结三个阶段的前置/后置反思配置
        - 可配置最大反思轮数，防止无限循环
    
    配置项:
        enabled: 总开关，控制是否启用反思机制
        max_rounds: 单点最大反思轮数，防止无限循环
        decompose: 拆解阶段配置 {"before": bool, "after": bool}
        execute: 执行阶段配置 {"before": bool, "after": bool}
        summarize: 总结阶段配置 {"before": bool, "after": bool}
    
    使用示例:
        >>> config = ReflectionConfig(enabled=True, max_rounds=3)
        >>> config.execute = {"before": True, "after": True}
    """
    
    enabled: bool = False
    max_rounds: int = 2
    
    # 各阶段开关配置
    decompose: Dict[str, bool] = field(default_factory=lambda: {"before": True, "after": False})
    execute: Dict[str, bool] = field(default_factory=lambda: {"before": True, "after": True})
    summarize: Dict[str, bool] = field(default_factory=lambda: {"before": False, "after": True})
    
    def __post_init__(self):
        """初始化后处理，确保配置项完整"""
        # 确保各阶段配置包含 before 和 after 键
        for stage_name in ["decompose", "execute", "summarize"]:
            stage_config = getattr(self, stage_name)
            if not isinstance(stage_config, dict):
                setattr(self, stage_name, {"before": False, "after": False})
            else:
                # 补充缺失的键
                if "before" not in stage_config:
                    stage_config["before"] = False
                if "after" not in stage_config:
                    stage_config["after"] = False
    
    def should_reflect(self, stage_name: str, timing: str) -> bool:
        """
        判断指定阶段是否应该反思
        
        Args:
            stage_name: 阶段名称 (decompose/execute/summarize)
            timing: 时机 (before/after)
            
        Returns:
            bool: 是否应该反思
            
        示例:
            >>> config.should_reflect("execute", "before")
            True
        """
        if not self.enabled:
            return False
        
        stage_config = getattr(self, stage_name, {})
        return stage_config.get(timing, False)
    
    def update_stage_config(self, stage_name: str, before: Optional[bool] = None, after: Optional[bool] = None):
        """
        更新指定阶段的配置
        
        Args:
            stage_name: 阶段名称
            before: 前置反思开关
            after: 后置反思开关
        """
        if stage_name not in ["decompose", "execute", "summarize"]:
            raise ValueError(f"无效的阶段名称: {stage_name}")
        
        stage_config = getattr(self, stage_name)
        if before is not None:
            stage_config["before"] = before
        if after is not None:
            stage_config["after"] = after
    
    def to_dict(self) -> Dict[str, Any]:
        """
        将配置转换为字典
        
        Returns:
            Dict: 配置字典
        """
        return {
            "enabled": self.enabled,
            "max_rounds": self.max_rounds,
            "decompose": self.decompose.copy(),
            "execute": self.execute.copy(),
            "summarize": self.summarize.copy()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReflectionConfig":
        """
        从字典创建配置
        
        Args:
            data: 配置字典
            
        Returns:
            ReflectionConfig: 配置对象
        """
        return cls(
            enabled=data.get("enabled", False),
            max_rounds=data.get("max_rounds", 2),
            decompose=data.get("decompose", {"before": True, "after": False}),
            execute=data.get("execute", {"before": True, "after": True}),
            summarize=data.get("summarize", {"before": False, "after": True})
        )
