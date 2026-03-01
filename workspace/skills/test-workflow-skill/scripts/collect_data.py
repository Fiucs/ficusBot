#!/usr/bin/env python3
"""
数据收集脚本 - 用于收集测试工作流所需的环境信息和数据

类级注释:
- 功能: 收集系统环境、目录结构和配置文件信息
- 核心方法: collect_env_info(), collect_directory_info(), collect_config_info()
- 配置项: 支持通过参数指定目标目录和配置文件路径
"""

import os
import sys
import json
import platform
from datetime import datetime
from pathlib import Path


def collect_env_info():
    """
    收集环境信息
    
    Returns:
        dict: 包含系统环境信息的字典
    """
    return {
        "platform": platform.system(),
        "platform_version": platform.version(),
        "python_version": platform.python_version(),
        "current_time": datetime.now().isoformat(),
        "working_directory": os.getcwd()
    }


def collect_directory_info(target_dir="."):
    """
    收集目录信息
    
    Args:
        target_dir (str): 目标目录路径，默认为当前目录
        
    Returns:
        dict: 包含目录结构信息的字典
    """
    target_path = Path(target_dir)
    
    if not target_path.exists():
        return {"error": f"目录不存在: {target_dir}"}
    
    files = []
    directories = []
    
    try:
        for item in target_path.iterdir():
            if item.is_file():
                files.append({
                    "name": item.name,
                    "size": item.stat().st_size,
                    "modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat()
                })
            elif item.is_dir():
                directories.append(item.name)
    except PermissionError as e:
        return {"error": f"权限错误: {str(e)}"}
    
    return {
        "target_directory": str(target_path.absolute()),
        "file_count": len(files),
        "directory_count": len(directories),
        "files": files[:10],  # 只返回前10个文件
        "directories": directories[:10]  # 只返回前10个目录
    }


def collect_config_info(config_path=None):
    """
    收集配置文件信息
    
    Args:
        config_path (str): 配置文件路径，可选
        
    Returns:
        dict: 包含配置信息的字典
    """
    if config_path is None:
        # 查找常见的配置文件
        possible_configs = ["config.json", "settings.json", ".env", "pyproject.toml"]
        for config in possible_configs:
            if Path(config).exists():
                config_path = config
                break
    
    if config_path is None or not Path(config_path).exists():
        return {"config_found": False, "message": "未找到配置文件"}
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return {
            "config_found": True,
            "config_path": config_path,
            "config_size": len(content),
            "config_preview": content[:200] + "..." if len(content) > 200 else content
        }
    except Exception as e:
        return {"config_found": False, "error": str(e)}


def main():
    """
    主函数 - 执行数据收集并输出JSON结果
    """
    # 收集所有信息
    result = {
        "collection_time": datetime.now().isoformat(),
        "environment": collect_env_info(),
        "directory": collect_directory_info(),
        "config": collect_config_info()
    }
    
    # 输出JSON格式的结果
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
