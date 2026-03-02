#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :sensitive.py
# @Time      :2026/03/02
# @Author    :Ficus

"""
敏感词过滤拦截器模块

功能说明:
    - 检测并替换敏感词
    - 不拦截消息，只修改内容

核心类:
    - SensitiveWordInterceptor: 敏感词过滤拦截器
"""

from loguru import logger
from ..base import Interceptor, InterceptResult


class SensitiveWordInterceptor(Interceptor):
    """
    敏感词过滤拦截器
    
    功能说明:
        - 检测并替换敏感词
        - 不拦截消息，只修改内容
    
    核心方法:
        - name: 拦截器名称
        - intercept: 执行敏感词过滤
    
    配置示例:
        interceptor = SensitiveWordInterceptor(
            words=["敏感词1", "敏感词2"],
            replace_char="***"
        )
    """
    
    def __init__(
        self, 
        words: list = None, 
        replace_char: str = "***"
    ):
        """
        初始化敏感词过滤拦截器。
        
        参数:
            words: 敏感词列表
            replace_char: 替换字符，默认 "***"
        """
        self.words = words or []
        self.replace_char = replace_char
    
    @property
    def name(self) -> str:
        """
        拦截器名称。
        
        返回:
            str: "sensitive_word"
        """
        return "sensitive_word"
    
    async def intercept(self, data: dict) -> InterceptResult:
        """
        执行敏感词过滤。
        
        检查并替换消息内容中的敏感词，不拦截消息。
        
        参数:
            data: 消息数据，需包含 content 字段
        
        返回:
            InterceptResult: 过滤结果（始终通过）
        """
        content = data.get("content", "")
        
        if not content or not isinstance(content, str):
            return InterceptResult.ok(data)
        
        # 检查并替换敏感词
        found_words = []
        for word in self.words:
            if word in content:
                found_words.append(word)
                content = content.replace(word, self.replace_char)
        
        if found_words:
            data["content"] = content
            logger.warning(
                f"[{self.name}] 发现敏感词: {found_words}"
            )
        
        return InterceptResult.ok(data)
