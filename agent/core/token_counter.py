#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :token_counter.py
# @Time      :2026/03/11
# @Author    :Ficus

"""
Token 和耗时统计器

核心功能:
    - 耗时统计：自动计算从开始到结束的时间
    - Token 累加：支持从 LLM 响应中提取或直接累加
    - 结果构建：统一构建包含统计信息的结果字典

设计原则:
    - 支持上下文管理器（with 语句）
    - 链式调用风格
    - 线程安全

使用示例:
    >>> with TokenCounter() as counter:
    ...     counter.add_usage(response)
    ...     return counter.build_result(content)
    
    >>> counter = TokenCounter().start()
    >>> counter.add_tokens(100, 50)
    >>> result = counter.build_result("回答内容")
"""

import time
from typing import Any, Dict, Optional, Tuple


class TokenCounter:
    """
    Token 和耗时统计器
    
    功能说明:
        - 耗时统计：自动计算从开始到结束的时间
        - Token 累加：支持从 LLM 响应中提取或直接累加
        - 结果构建：统一构建包含统计信息的结果字典
    
    核心方法:
        - start: 开始计时
        - add_usage: 从 LLM 响应中累加 token
        - add_tokens: 直接累加 token
        - build_result: 构建结果字典
    
    配置项:
        - 无配置项，纯工具类
    
    使用方式:
        1. 上下文管理器: with TokenCounter() as counter:
        2. 手动调用: counter = TokenCounter().start()
    """
    
    def __init__(self):
        """
        初始化统计器
        """
        self._start_time: float = 0.0
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0
        self._is_started: bool = False
    
    def start(self) -> "TokenCounter":
        """
        开始计时
        
        Returns:
            self，支持链式调用
        """
        self._start_time = time.time()
        self._is_started = True
        return self
    
    def add_usage(self, response: Any) -> "TokenCounter":
        """
        从 LLM 响应中累加 token
        
        Args:
            response: LLM 响应对象，需要有 usage 属性
        
        Returns:
            self，支持链式调用
        """
        if hasattr(response, 'usage') and response.usage:
            self._total_prompt_tokens += response.usage.prompt_tokens or 0
            self._total_completion_tokens += response.usage.completion_tokens or 0
        return self
    
    def add_tokens(self, prompt_tokens: int, completion_tokens: int) -> "TokenCounter":
        """
        直接累加 token
        
        Args:
            prompt_tokens: 输入 token 数
            completion_tokens: 输出 token 数
        
        Returns:
            self，支持链式调用
        """
        self._total_prompt_tokens += prompt_tokens
        self._total_completion_tokens += completion_tokens
        return self
    
    def merge(self, other: "TokenCounter") -> "TokenCounter":
        """
        合并另一个统计器的数据
        
        Args:
            other: 另一个 TokenCounter 实例
        
        Returns:
            self，支持链式调用
        """
        self._total_prompt_tokens += other._total_prompt_tokens
        self._total_completion_tokens += other._total_completion_tokens
        return self
    
    @property
    def elapsed_time(self) -> float:
        """
        获取耗时（秒）
        
        Returns:
            从开始到现在的时间（秒），如果未开始则返回 0
        """
        if not self._is_started:
            return 0.0
        return time.time() - self._start_time
    
    @property
    def total_prompt_tokens(self) -> int:
        """
        获取总输入 token 数
        
        Returns:
            总输入 token 数
        """
        return self._total_prompt_tokens
    
    @property
    def total_completion_tokens(self) -> int:
        """
        获取总输出 token 数
        
        Returns:
            总输出 token 数
        """
        return self._total_completion_tokens
    
    @property
    def total_tokens(self) -> int:
        """
        获取总 token 数
        
        Returns:
            总 token 数（输入 + 输出）
        """
        return self._total_prompt_tokens + self._total_completion_tokens
    
    def get_tokens(self) -> Tuple[int, int]:
        """
        获取 token 统计元组
        
        Returns:
            (prompt_tokens, completion_tokens) 元组
        """
        return (self._total_prompt_tokens, self._total_completion_tokens)
    
    def build_result(self, content: str, elapsed_time: Optional[float] = None) -> dict:
        """
        构建结果字典
        
        Args:
            content: 回复内容
            elapsed_time: 耗时（可选，默认使用当前耗时）
        
        Returns:
            结果字典，包含 content, elapsed_time, total_prompt_tokens, total_completion_tokens
        """
        return {
            "content": content,
            "elapsed_time": elapsed_time if elapsed_time is not None else self.elapsed_time,
            "total_prompt_tokens": self._total_prompt_tokens,
            "total_completion_tokens": self._total_completion_tokens
        }
    
    def __enter__(self) -> "TokenCounter":
        """
        上下文管理器入口
        
        Returns:
            self
        """
        return self.start()
    
    def __exit__(self, *args):
        """
        上下文管理器出口
        """
        pass
    
    def __repr__(self) -> str:
        """
        字符串表示
        
        Returns:
            包含统计信息的字符串
        """
        return (
            f"TokenCounter(elapsed={self.elapsed_time:.2f}s, "
            f"prompt={self._total_prompt_tokens}, "
            f"completion={self._total_completion_tokens})"
        )
