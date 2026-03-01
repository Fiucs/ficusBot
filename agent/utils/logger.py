#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
日志管理模块

功能说明:
    - 统一管理日志配置
    - 支持文件日志输出（带轮转）
    - 支持控制台彩色输出
    - 支持多级别日志过滤
    - 支持对话历史日志过滤（控制台显示，文件不记录）
    - 配置化初始化

使用示例:
    from agent.utils.logger import LoggerManager
    
    # 初始化日志配置
    LoggerManager.setup(
        enable_file=True,
        log_dir="./logs",
        level="INFO"
    )
    
    # 获取日志实例
    logger = LoggerManager.get_logger()
    logger.info("这是一条日志")
"""

import os
import sys
from typing import Optional, Callable
from pathlib import Path
from loguru import logger


def _filter_conversation_history(record: dict) -> bool:
    """
    过滤对话历史日志（用于文件日志处理器）。
    
    功能说明:
        - 过滤掉以 "[历史" 开头的日志消息
        - 这些日志只在控制台显示，不记录到文件
    
    参数:
        record: loguru 日志记录对象
    
    返回:
        bool: True 表示保留该日志，False 表示过滤掉
    """
    message = record["message"]
    if message.startswith("[历史"):
        return False
    return True


class LoggerManager:
    """
    日志管理器，统一管理日志配置。
    
    功能说明:
        - 文件日志输出（支持轮转）
        - 控制台彩色输出
        - 多级别日志过滤
        - 对话历史日志过滤（控制台显示，文件不记录）
        - 配置化初始化
    
    核心方法:
        - setup: 初始化日志配置
        - get_logger: 获取日志实例
        - add_file_handler: 添加文件日志处理器
    
    配置项:
        - enable_file: 是否启用文件日志
        - log_dir: 日志文件目录
        - level: 日志级别
        - rotation: 日志轮转策略
        - retention: 日志保留时间
        - format: 日志格式
        - enable_console: 是否启用控制台输出
        - console_level: 控制台日志级别（默认DEBUG，显示更多）
    """
    
    _initialized: bool = False
    _log_dir: str = "./logs"
    _level: str = "INFO"
    
    @classmethod
    def setup(
        cls,
        enable_file: bool = True,
        log_dir: str = "./logs",
        level: str = "INFO",
        rotation: str = "10 MB",
        retention: str = "7 days",
        format: Optional[str] = None,
        enable_console: bool = True,
        console_format: Optional[str] = None,
        console_level: Optional[str] = None
    ) -> None:
        """
        初始化日志配置。
        
        参数:
            enable_file: 是否启用文件日志，默认True
            log_dir: 日志文件目录，默认"./logs"
            level: 文件日志级别，默认"INFO"
            rotation: 日志轮转策略，默认"10 MB"
            retention: 日志保留时间，默认"7 days"
            format: 文件日志格式，默认使用标准格式
            enable_console: 是否启用控制台输出，默认True
            console_format: 控制台日志格式，默认使用简洁格式
            console_level: 控制台日志级别，默认DEBUG（显示更多日志）
        """
        if cls._initialized:
            logger.warning("LoggerManager 已初始化，跳过重复初始化")
            return
        
        cls._log_dir = log_dir
        cls._level = level
        
        logger.remove()
        
        file_format = format or (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )
        
        console_fmt = console_format or (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<level>{message}</level>"
        )
        
        if enable_console:
            console_lvl = console_level or "DEBUG"
            logger.add(
                sys.stderr,
                format=console_fmt,
                level=console_lvl,
                colorize=True,
                enqueue=False
            )
        
        if enable_file:
            log_path = Path(log_dir)
            log_path.mkdir(parents=True, exist_ok=True)
            
            logger.add(
                os.path.join(log_dir, "ficusbot_{time:YYYY-MM-DD}.log"),
                format=file_format,
                level=level,
                rotation=rotation,
                retention=retention,
                encoding="utf-8",
                enqueue=False,
                diagnose=False,
                filter=_filter_conversation_history
            )
            
            logger.add(
                os.path.join(log_dir, "error_{time:YYYY-MM-DD}.log"),
                format=file_format,
                level="ERROR",
                rotation=rotation,
                retention=retention,
                encoding="utf-8",
                enqueue=False,
                diagnose=True,
                backtrace=True
            )
        
        cls._initialized = True
        logger.info(f"日志系统初始化完成: 文件日志={enable_file}, 目录={log_dir}, 文件级别={level}, 控制台级别={console_level or 'DEBUG'}")
    
    @classmethod
    def get_logger(cls):
        """
        获取日志实例。
        
        返回:
            logger: loguru 日志实例
        """
        return logger
    
    @classmethod
    def add_file_handler(
        cls,
        file_path: str,
        level: str = "DEBUG",
        rotation: Optional[str] = None,
        retention: Optional[str] = None,
        format: Optional[str] = None,
        filter_func: Optional[Callable[[dict], bool]] = None
    ) -> int:
        """
        添加额外的文件日志处理器。
        
        参数:
            file_path: 日志文件路径
            level: 日志级别，默认DEBUG
            rotation: 日志轮转策略
            retention: 日志保留时间
            format: 日志格式
            filter_func: 日志过滤函数
        
        返回:
            int: 处理器ID
        """
        file_format = format or (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )
        
        handler_id = logger.add(
            file_path,
            format=file_format,
            level=level,
            rotation=rotation,
            retention=retention,
            encoding="utf-8",
            enqueue=False,
            filter=filter_func
        )
        
        return handler_id
    
    @classmethod
    def remove_handler(cls, handler_id: int) -> None:
        """
        移除指定的日志处理器。
        
        参数:
            handler_id: 处理器ID
        """
        logger.remove(handler_id)
    
    @classmethod
    def is_initialized(cls) -> bool:
        """
        检查日志系统是否已初始化。
        
        返回:
            bool: 是否已初始化
        """
        return cls._initialized


def setup_logger_from_config(config: dict) -> None:
    """
    从配置字典初始化日志系统。
    
    参数:
        config: 配置字典，应包含 "log" 键
    """
    log_config = config.get("log", {})
    
    LoggerManager.setup(
        enable_file=log_config.get("enable_file", True),
        log_dir=log_config.get("log_dir", "./logs"),
        level=log_config.get("level", "INFO"),
        rotation=log_config.get("rotation", "10 MB"),
        retention=log_config.get("retention", "7 days"),
        format=log_config.get("format"),
        enable_console=log_config.get("enable_console", True),
        console_format=log_config.get("console_format"),
        console_level=log_config.get("console_level", "DEBUG")
    )
