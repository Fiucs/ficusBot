#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :embedding_service.py
# @Time      :2026/03/12
# @Author    :Ficus

"""
嵌入服务模块

提供文本嵌入向量生成功能，支持多种嵌入模型：
- HuggingFace 本地模型（sentence-transformers）
- GGUF 格式模型（llama-cpp-python）
- API 嵌入服务（OpenAI 兼容接口）

核心方法:
    embed: 单文本嵌入（异步）
    embed_batch: 批量文本嵌入（异步）
    embed_batch_sync: 批量同步嵌入
    get_embedding_dim: 获取嵌入维度

Attributes:
    embedding_type: 嵌入类型（local/gguf/api/none）
    model: 嵌入模型实例
    client: API 客户端（仅 API 类型）
"""

import os
import asyncio
import numpy as np
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from loguru import logger


class EmbeddingService:
    """
    嵌入服务类
    
    提供文本嵌入向量生成功能，支持多种嵌入模型后端。
    
    核心方法:
        embed: 单文本嵌入（异步）
        embed_batch: 批量文本嵌入（异步）
        embed_batch_sync: 批量同步嵌入
        get_embedding_dim: 获取嵌入维度
    
    Attributes:
        embedding_type: 嵌入类型（local/gguf/api/none）
        model: 嵌入模型实例
        client: API 客户端（仅 API 类型）
        model_name: 模型名称（仅 API 类型）
        batch_size: 批处理大小（仅 GGUF 类型）
    """
    
    def __init__(self, config: Dict, workspace_root: str = "."):
        """
        初始化嵌入服务
        
        根据 local_model 扩展名自动判断格式：
        - .gguf 结尾：使用 llama-cpp-python 加载
        - 其他：使用 sentence-transformers 加载（HuggingFace 格式）
        
        Args:
            config: 嵌入服务配置，包含：
                - provider: 提供者（local/openai/zhipu/qwen/deepseek/custom）
                - local_model: 本地模型路径或名称
                - cache_folder: HuggingFace 缓存目录
                - api_key: API 密钥
                - model: API 模型名称
                - base_url: 自定义 API 地址
            workspace_root: 工作区根目录
        """
        self._workspace_root = workspace_root
        self._config = config
        
        provider = config.get("provider", "local")
        
        if provider == "local":
            local_model = config.get("local_model", "BAAI/bge-small-zh-v1.5")
            
            if local_model.endswith(".gguf"):
                self._init_gguf_embedding(local_model)
            else:
                self._init_huggingface_embedding(local_model, config)
        else:
            self._init_api_embedding(config)
    
    def _resolve_path(self, path: str) -> str:
        """
        解析路径，支持变量替换
        
        Args:
            path: 原始路径
        
        Returns:
            解析后的绝对路径
        """
        if not path:
            return path
        
        path = path.replace("{workspace_root}", self._workspace_root)
        
        if not os.path.isabs(path):
            path = os.path.abspath(path)
        
        return path
    
    def _init_gguf_embedding(self, model_path: str):
        """初始化 GGUF 格式嵌入模型"""
        try:
            from llama_cpp import Llama
            
            model_path = self._resolve_path(model_path)
            
            if not os.path.exists(model_path):
                logger.warning(f"GGUF 模型文件不存在: {model_path}")
                self.embedding_type = "none"
                return
            
            logger.info(f"加载 GGUF 嵌入模型: {model_path}")
            logger.info(f"正在初始化模型，请稍候...")
            
            import sys
            
            old_stderr = sys.stderr
            sys.stderr = open(os.devnull, 'w')
            
            try:
                llm = Llama(
                    model_path=model_path,
                    embedding=True,
                    n_ctx=4096,
                    n_batch=2048,
                    n_ubatch=2048,
                    n_gpu_layers=-1,
                    n_threads=8,
                    verbose=False
                )
            finally:
                sys.stderr.close()
                sys.stderr = old_stderr
            
            self.embedding_type = "gguf"
            self.model = llm
            self.batch_size = 1
            logger.info(f"GGUF 嵌入模型加载完成")
        except ImportError:
            logger.warning("llama-cpp-python 未安装，GGUF 嵌入功能将不可用。安装: pip install llama-cpp-python")
            self.embedding_type = "none"
        except Exception as e:
            logger.warning(f"加载 GGUF 模型失败: {e}")
            self.embedding_type = "none"
    
    def _init_huggingface_embedding(self, model_name: str, config: Dict):
        """初始化 HuggingFace 格式嵌入模型"""
        try:
            from sentence_transformers import SentenceTransformer
            
            cache_folder = config.get("cache_folder")
            
            if cache_folder:
                cache_folder = self._resolve_path(cache_folder)
                logger.info(f"加载 HuggingFace 嵌入模型: {model_name}, 缓存目录: {cache_folder}")
                model = SentenceTransformer(model_name, cache_folder=cache_folder)
            else:
                logger.info(f"加载 HuggingFace 嵌入模型: {model_name}")
                model = SentenceTransformer(model_name)
            
            self.embedding_type = "local"
            self.model = model
        except ImportError:
            logger.warning("sentence-transformers 未安装，嵌入功能将不可用")
            self.embedding_type = "none"
    
    def _init_api_embedding(self, config: Dict):
        """初始化 API 嵌入服务"""
        try:
            from openai import AsyncOpenAI
            
            provider = config.get("provider", "openai")
            base_urls = {
                "openai": None,
                "zhipu": "https://open.bigmodel.cn/api/paas/v4/",
                "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "deepseek": "https://api.deepseek.com/v1",
                "custom": config.get("base_url")
            }
            
            self.embedding_type = "api"
            self.client = AsyncOpenAI(
                api_key=config.get("api_key", ""),
                base_url=base_urls.get(provider)
            )
            self.model_name = config.get("model", "text-embedding-3-small")
        except ImportError:
            logger.warning("openai 未安装，API 嵌入功能将不可用")
            self.embedding_type = "none"
    
    def get_embedding_dim(self) -> int:
        """
        获取嵌入向量维度
        
        Returns:
            嵌入向量维度
        """
        if self.embedding_type == "none":
            return 384
        
        try:
            if self.embedding_type == "local":
                sample_embedding = self.model.encode("test").tolist()
                return len(sample_embedding) if sample_embedding else 384
            elif self.embedding_type == "gguf":
                sample_embedding = self.model.embed("test")
                return len(sample_embedding) if sample_embedding else 384
            elif self.embedding_type == "api":
                sample_embedding = asyncio.run(self.embed("test"))
                return len(sample_embedding) if sample_embedding else 384
            return 384
        except Exception as e:
            logger.warning(f"获取嵌入维度失败: {e}")
            return 384
    
    async def embed(self, text: str) -> List[float]:
        """
        获取嵌入向量（归一化）
        
        Args:
            text: 输入文本
        
        Returns:
            归一化的嵌入向量列表
        """
        if self.embedding_type == "local":
            embedding = self.model.encode(text)
        elif self.embedding_type == "gguf":
            embedding = self.model.embed(text)
        elif self.embedding_type == "api":
            resp = await self.client.embeddings.create(
                input=text,
                model=self.model_name
            )
            embedding = resp.data[0].embedding
        else:
            return []
        
        vec = np.array(embedding)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量获取嵌入向量（归一化）
        
        Args:
            texts: 输入文本列表
        
        Returns:
            归一化的嵌入向量列表的列表
        """
        if self.embedding_type == "local":
            embeddings = self.model.encode(texts)
        elif self.embedding_type == "gguf":
            batch_size = getattr(self, 'batch_size', 8)
            embeddings = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                result = self.model.create_embedding(batch)
                embeddings.extend([item["embedding"] for item in result["data"]])
        elif self.embedding_type == "api":
            embeddings = await asyncio.gather(*[self.embed(t) for t in texts])
            return embeddings
        else:
            return [[] for _ in texts]
        
        results = []
        for emb in embeddings:
            vec = np.array(emb)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            results.append(vec.tolist())
        
        return results
    
    def embed_batch_sync(self, texts: List[str]) -> List[List[float]]:
        """
        批量同步获取嵌入向量（用于迁移等场景）
        
        Args:
            texts: 输入文本列表
        
        Returns:
            归一化的嵌入向量列表的列表
        """
        if self.embedding_type == "local":
            embeddings = self.model.encode(texts)
        elif self.embedding_type == "gguf":
            batch_size = getattr(self, 'batch_size', 8)
            embeddings = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                result = self.model.create_embedding(batch)
                embeddings.extend([item["embedding"] for item in result["data"]])
        elif self.embedding_type == "api":
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            
            if loop and loop.is_running():
                with ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.embed_batch(texts)
                    )
                    return future.result()
            else:
                return asyncio.run(self.embed_batch(texts))
        else:
            return [[] for _ in texts]
        
        results = []
        for emb in embeddings:
            vec = np.array(emb)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            results.append(vec.tolist())
        
        return results
