#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :llmclient.py
# @Time      :2026/02/19 20:54:35
# @Author    :Ficus


# ======================================
# LLM客户端
# 用于加载各个模型的配置，并调用LLM API
# ======================================

import time
from typing import Any, Dict, List, Optional, Union

from agent.config.configloader import GLOBAL_CONFIG
from loguru import logger
from colorama import init, Fore, Style

# 直接导入 litellm，并记录导入时间
_litellm_import_start = time.time()
from litellm import completion
from litellm.exceptions import APIError, AuthenticationError, InvalidRequestError, RateLimitError
_litellm_import_time = time.time() - _litellm_import_start

class LLMClient:
    """
    LLM客户端类
    
    功能说明:
        - 管理LLM模型配置和切换
        - 提供统一的chat_completion接口调用大模型
        - 支持多模型提供商(OpenAI、通义千问、Ollama等)
        - 获取模型上下文窗口大小
        - 计算消息的 token 数量
        - 支持配置 extra_body 参数（厂商专属参数透传）
    
    核心方法:
        - chat_completion: 调用大模型进行对话补全
        - switch_model: 切换当前使用的模型
        - list_models: 列出所有可用模型
        - reload_config: 重新加载配置
        - get_context_window: 获取当前模型的上下文窗口大小
        - count_tokens: 计算消息列表的 token 数量
    
    配置项:
        - current_model_alias: 当前模型别名
        - current_model_config: 当前模型配置字典
        - extra_body: 厂商专属参数，如 DashScope 的 enable_search
    """
    
    MODEL_CONTEXT_WINDOWS = {
        "gpt-3.5-turbo": 16385,
        "gpt-3.5-turbo-16k": 16385,
        "gpt-4": 8192,
        "gpt-4-32k": 32768,
        "gpt-4-turbo": 128000,
        "gpt-4-turbo-preview": 128000,
        "gpt-4o": 128000,
        "gpt-4o-mini": 128000,
        "gpt-4.1": 1047576,
        "gpt-4.1-mini": 1047576,
        "gpt-4.1-nano": 1047576,
        "o1": 200000,
        "o1-mini": 128000,
        "o1-preview": 128000,
        "claude-3-opus": 200000,
        "claude-3-sonnet": 200000,
        "claude-3-haiku": 200000,
        "claude-3-5-sonnet": 200000,
        "claude-3-5-haiku": 200000,
        "qwen-max": 32768,
        "qwen-plus": 131072,
        "qwen-turbo": 8192,
        "qwen2.5": 131072,
        "qwen2.5-72b": 131072,
        "qwen2.5-32b": 131072,
        "qwen2.5-14b": 131072,
        "qwen2.5-7b": 131072,
        "glm-4": 128000,
        "glm-4-plus": 128000,
        "glm-4-air": 128000,
        "glm-4-flash": 128000,
        "glm-4.6v": 131072,
        "deepseek-chat": 64000,
        "deepseek-coder": 16384,
        "deepseek-reasoner": 64000,
        "llama3": 8192,
        "llama3:8b": 8192,
        "llama3:70b": 8192,
        "llama3.1": 131072,
        "llama3.1:8b": 131072,
        "llama3.1:70b": 131072,
        "llama3.2": 131072,
        "llama3.2:1b": 131072,
        "llama3.2:3b": 131072,
        "mistral-small": 32000,
        "mistral-medium": 32000,
        "mistral-large": 128000,
        "codestral": 32000,
        "gemini-1.5-pro": 1048576,
        "gemini-1.5-flash": 1048576,
        "gemini-2.0-flash": 1048576,
    }
    
    def __init__(self, default_model: Optional[str] = None):
        """
        初始化LLM客户端
        
        Args:
            default_model: 默认模型别名，为None时从全局配置读取
        """
        start_time = time.time()
        self.current_model_alias = default_model or GLOBAL_CONFIG.get("llm.default_model")
        self.current_model_config = GLOBAL_CONFIG.get_model_config(self.current_model_alias)
        self._preset_params: Dict[str, Any] = {}
        init_time = time.time() - start_time
        logger.info(f"{Fore.GREEN}✅ LLM客户端初始化完成，当前模型：{self.current_model_alias}{Style.RESET_ALL}")
        logger.info(f"{Fore.CYAN}📊 LLM客户端初始耗时：{_litellm_import_time:.3f}秒")   
    
    def apply_preset(self, preset_params: Dict[str, Any]):
        """
        应用预设参数到当前配置
        
        Args:
            preset_params: 预设参数字典，如 {"temperature": 0.5, "max_tokens": 16000}
        """
        self._preset_params = preset_params.copy()
        logger.info(f"{Fore.CYAN}[LLMClient] 应用预设参数: {preset_params}{Style.RESET_ALL}")   
        
    def reload_config(self):
        """
        重新加载配置
        
        当配置文件变更后调用此方法更新模型设置
        如果当前模型被移除，自动切换到默认模型
        """
        GLOBAL_CONFIG.reload()
        all_models = GLOBAL_CONFIG.list_all_models()
        if self.current_model_alias not in all_models:
            self.current_model_alias = GLOBAL_CONFIG.get("llm.default_model")
            logger.warning(f"{Fore.YELLOW}⚠️  当前模型已移除，自动切换到默认模型：{self.current_model_alias}{Style.RESET_ALL}")
        self.current_model_config = GLOBAL_CONFIG.get_model_config(self.current_model_alias)
        self._preset_params = {}
        logger.info(f"{Fore.GREEN}✅ LLM配置重载完成，当前模型：{self.current_model_alias}{Style.RESET_ALL}")

    def switch_model(self, full_alias: str) -> Dict[str, Any]:
        """
        切换当前使用的模型
        
        Args:
            full_alias: 模型完整别名，如 "openai/gpt-4"
            
        Returns:
            Dict包含status和message字段
            
        Example:
            >>> client.switch_model("openai/gpt-4")
            {"status": "success", "message": "模型切换成功", "current_model": "openai/gpt-4"}
        """
        model_config = GLOBAL_CONFIG.get_model_config(full_alias)
        if not model_config:
            all_models = list(GLOBAL_CONFIG.list_all_models().keys())
            return {"status": "error", "message": f"模型 {full_alias} 不存在，可用模型：{all_models}"}
        self.current_model_alias = full_alias
        self.current_model_config = model_config
        return {
            "status": "success",
            "message": f"模型切换成功，当前模型：{full_alias}",
            "current_model": full_alias
        }
    
    def list_models(self) -> Dict[str, Any]:
        """
        列出所有已配置的模型
        
        Returns:
            Dict包含所有模型信息，每个模型包含litellm_model、provider、remark、is_current字段
        """
        all_models = GLOBAL_CONFIG.list_all_models()
        result = {}
        for full_alias, config in all_models.items():
            result[full_alias] = {
                "litellm_model": config.get("litellm_model_name", ""),
                "provider": config.get("provider", ""),
                "remark": config.get("remark", "无备注"),
                "is_current": full_alias == self.current_model_alias
            }
        return result
    
    def get_context_window(self) -> int:
        """
        获取当前模型的上下文窗口大小。
        
        查找逻辑:
            1. 优先从模型配置中读取 context_window 字段
            2. 从全局配置 llm.global.context_window 读取
            3. 从模型名称中匹配内置的上下文窗口映射表
            4. 默认返回 128000（128k）
        
        Returns:
            int: 上下文窗口大小（token数）
            
        Example:
            >>> client.get_context_window()
            128000
        """
        if self.current_model_config:
            if "context_window" in self.current_model_config:
                return self.current_model_config["context_window"]
        
        global_context_window = GLOBAL_CONFIG.get("llm.global.context_window")
        if global_context_window:
            return global_context_window
        
        model_name = ""
        if self.current_model_config:
            model_name = self.current_model_config.get("model_name", "")
            if not model_name:
                model_name = self.current_model_config.get("litellm_model_name", "")
        
        model_name_lower = model_name.lower()
        
        for key, window in self.MODEL_CONTEXT_WINDOWS.items():
            if key.lower() in model_name_lower or model_name_lower in key.lower():
                return window
        
        return 128000
    
    def count_tokens(self, messages: List[Dict[str, str]], model: Optional[str] = None) -> int:
        """
        计算消息列表的 token 数量。
        
        Args:
            messages: 对话消息列表
            model: 模型名称，None 则使用当前模型
            
        Returns:
            int: token 数量
        """
        try:
            import litellm
            use_model = model or self._get_tokenizer_model()
            return litellm.token_counter(messages=messages, model=use_model)
        except Exception as e:
            logger.warning(f"[Token计算] litellm计算失败: {e}，使用估算方法")
            return self._estimate_tokens(messages)
    
    def _get_tokenizer_model(self) -> str:
        """
        获取用于 token 计算的模型名称。
        
        不同模型使用不同的 tokenizer，这里返回一个兼容的模型名称。
        
        Returns:
            str: 模型名称
        """
        if self.current_model_config:
            model_name = self.current_model_config.get("model_name", "")
            model_name_lower = model_name.lower()
            
            if "gpt" in model_name_lower or "openai" in model_name_lower:
                return "gpt-4o"
            elif "claude" in model_name_lower:
                return "claude-3-opus-20240229"
            elif "qwen" in model_name_lower:
                return "gpt-4o"
            elif "glm" in model_name_lower or "zhipu" in model_name_lower:
                return "gpt-4o"
            elif "deepseek" in model_name_lower:
                return "gpt-4o"
        
        return "gpt-4o"
    
    def _estimate_tokens(self, messages: List[Dict[str, str]]) -> int:
        """
        估算 token 数量（备用方法）。
        
        使用简单的字符估算：约3字符/token。
        
        Args:
            messages: 对话消息列表
            
        Returns:
            int: 估算的 token 数量
        """
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "") or ""
            total_chars += len(content)
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    if tc.get("function"):
                        total_chars += len(str(tc["function"]))
        return int(total_chars / 3)

 
    
    THINKING_PROVIDERS = {
        "deepseek": {
            "mode": "thinking",
            "supports_budget": False
        },
        "anthropic": {
            "mode": "thinking",
            "supports_budget": True,
            "default_budget_tokens": 1024
        },
        "openai": {
            "mode": "reasoning_effort",
            "default_effort": "medium",
            "supported_models": ["o1", "o3", "o4", "gpt-5"]
        },
        "zai": {"mode": "thinking", "supports_budget": False},
        "glm": {"mode": "thinking", "supports_budget": False},
        "qwen": {"mode": "thinking", "supports_budget": False},
        "tongyi": {"mode": "thinking", "supports_budget": False},
        "volcengine": {"mode": "thinking", "supports_budget": False},   # 新增
        "lm_studio": {"mode": "thinking", "supports_budget": False},
        "moonshot": {"mode": "thinking", "supports_budget": False},
        "kimi": {"mode": "thinking", "supports_budget": False},
        "gemini": {
            "mode": "thinking",
            "supports_budget": True,
            "default_budget_tokens": 1024
        },
        "google": {  # 备用
            "mode": "thinking",
            "supports_budget": True,
            "default_budget_tokens": 1024
        }
    }
    
    def _merge_extra_body(self, config: Dict[str, Any], kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        合并配置中的 extra_body 参数到请求参数
        
        参数:
            config: 模型配置字典
            kwargs: 当前请求参数
            
        返回:
            更新后的 kwargs
            
        配置示例:
            "models": {
                "qwen-plus": {
                    "extra_body": {
                        "enable_search": true
                    }
                }
            }
        """
        extra_body_config = config.get("extra_body")
        if not extra_body_config or not isinstance(extra_body_config, dict):
            return kwargs
        
        if "extra_body" not in kwargs:
            kwargs["extra_body"] = {}
        
        kwargs["extra_body"].update(extra_body_config)
        logger.debug(f"[ExtraBody] 合并配置: {extra_body_config}")
        
        return kwargs
    
    def _build_thinking_params(self, config: Dict[str, Any], kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        根据厂商配置构建 thinking 参数（2026-03-04 终极兼容版）
        支持 lm_studio / qwen 本地模型正确关闭思考
        """
        thinking_config = config.get("thinking")
        if not thinking_config:
            return kwargs

        # ==================== 增强 provider 检测 ====================
        provider = config.get("provider", "").lower()
        model_name = (config.get("model_name", "") or config.get("litellm_model_name", "")).lower()
        
        if not provider:
            if any(x in model_name for x in ["glm", "zai"]):
                provider = "zai"
            elif "deepseek" in model_name:
                provider = "deepseek"
            elif any(x in model_name for x in ["qwen", "lm_studio"]):
                provider = "qwen"          # ← lm_studio 的 qwen 模型统一走这里
            elif any(x in model_name for x in ["doubao", "volcengine"]):
                provider = "volcengine"
            elif "gemini" in model_name:
                provider = "gemini"
            # 其他保持 config 里的 provider
        
        provider_config = self.THINKING_PROVIDERS.get(provider, {})
        # ===========================================================

        enabled = thinking_config.get("enabled", True)
        mode = thinking_config.get("mode", provider_config.get("mode", "thinking"))

        if mode == "thinking":
            if enabled:
                thinking_param = {"type": "enabled"}
                if provider_config.get("supports_budget", False):
                    budget_tokens = thinking_config.get(
                        "budget_tokens", 
                        provider_config.get("default_budget_tokens", 1024)
                    )
                    thinking_param["budget_tokens"] = budget_tokens
            else:
                thinking_param = {"type": "disabled"}

            # ==================== 厂商专属注入 ====================
            if provider in ("zai", "glm", "deepseek", "volcengine"):
                # 这些厂商必须用 thinking 对象
                if "extra_body" not in kwargs:
                    kwargs["extra_body"] = {}
                kwargs["extra_body"]["thinking"] = thinking_param
                logger.debug(f"[Thinking] {provider}: extra_body.thinking = {thinking_param}")

            elif provider in ("qwen", "tongyi", "lm_studio"):
                # Qwen / 通义 / LM Studio 本地 Qwen → 用 enable_thinking
                if "extra_body" not in kwargs:
                    kwargs["extra_body"] = {}
                kwargs["extra_body"]["enable_thinking"] = enabled
                logger.debug(f"[Thinking] {provider}: extra_body.enable_thinking = {enabled}")

            elif provider in ("gemini", "google"):
                # Gemini 用 thinking_budget
                budget = thinking_config.get("budget_tokens", 1024) if enabled else 0
                kwargs["thinking_budget"] = budget
                logger.debug(f"[Thinking] gemini: thinking_budget = {budget}")

            else:
                # Anthropic / OpenAI 等走顶层
                kwargs["thinking"] = thinking_param
                logger.debug(f"[Thinking] {provider}: thinking={thinking_param}")

        elif mode == "reasoning_effort":
            if enabled:
                effort = thinking_config.get("effort", provider_config.get("default_effort", "medium"))
                supported = provider_config.get("supported_models", [])
                is_reasoning_model = any(s in model_name for s in supported)
                if is_reasoning_model:
                    kwargs["reasoning_effort"] = effort
                    logger.debug(f"[Thinking] reasoning_effort={effort}")

        return kwargs
    def chat_completion(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, stream: Optional[bool] = None
                            ,custom_model: Optional[str] = None):
        """
        调用大模型进行对话补全
        
        Args:
            messages: 对话消息列表，支持多模态格式
                - 文本格式: {"role": "user", "content": "文本"}
                - 多模态格式: {"role": "user", "content": [{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {"url": "..."}}]}
            tools: 可选的工具定义列表，用于Function Calling
            stream: 是否使用流式输出，None则使用配置默认值
            custom_model: 自定义模型名称，覆盖当前配置
            
        Returns:
            大模型响应对象
            
        Raises:
            Exception: 各种API调用错误(认证失败、频率限制、参数错误等)
            
        Example:
            >>> messages = [{"role": "user", "content": "你好"}]
            >>> response = client.chat_completion(messages)
            >>> print(response.choices[0].message.content)
        """
        try:
            config = self.current_model_config or {}
            use_stream = stream if stream is not None else config.get("stream", False)
            if tools:
                use_stream = False
            current_model_name = custom_model or config.get("litellm_model_name", "")    

            kwargs = {
                "model": current_model_name,
                "messages": messages,
                "api_key": config.get("api_key", ""),
                "temperature": self._preset_params.get("temperature", config.get("temperature", 0.7)),
                "max_tokens": self._preset_params.get("max_tokens", config.get("max_tokens", 1024)),
                "timeout": self._preset_params.get("timeout", config.get("timeout", 60)),
                "stream": use_stream,
                "drop_params": config.get("drop_params", True)
            }
            api_base = config.get("api_base", "")
            if api_base:
                kwargs["api_base"] = api_base
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            
            kwargs = self._build_thinking_params(config, kwargs)
            kwargs = self._merge_extra_body(config, kwargs)

            import json
            import base64
            
            for msg in messages:
                if isinstance(msg.get("content"), list):
                    for item in msg.get("content", []):
                        if item.get("type") == "image_url":
                            img_url = item.get("image_url", {}).get("url", "")
                            if img_url.startswith("data:"):
                                logger.info(f"[LLMClient] 📷 发送图片， Base64 长度: {len(img_url)}")
                                try:
                                    header, data = img_url.split(",", 1)
                                    mime_part = header.split(":")[1] if ":" in header else "image/jpeg"
                                    logger.info(f"[LLMClient] 📷 MIME 类型: {mime_part}")
                                    img_data = base64.b64decode(data)
                                    logger.info(f"[LLMClient] 📷 图片大小: {len(img_data)} bytes")
                                except Exception as e:
                                    logger.error(f"[LLMClient] ❌ 图片解析失败: {e}")
            
            return completion(**kwargs)

        except AuthenticationError:
            raise Exception(f"模型 {self.current_model_alias} API Key认证失败")
        except RateLimitError:
            raise Exception(f"模型 {self.current_model_alias} 请求频率超限")
        except InvalidRequestError as e:
            raise Exception(f"模型 {self.current_model_alias} 请求参数错误：{str(e)}")
        except APIError as e:
            raise Exception(f"模型 {self.current_model_alias} API调用失败：{str(e)}")
        except Exception as e:
            raise Exception(f"大模型调用失败：{str(e)}")
