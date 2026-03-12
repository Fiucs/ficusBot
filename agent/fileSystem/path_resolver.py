import os
import re
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path


class PathResolver:
    """
    智能路径解析器

    功能说明：
    - 支持语义路径转换（如 ~、desktop、documents 等）
    - 支持相对路径转绝对路径
    - 支持路径规范化（处理 /、\\ 等路径分隔符）
    注意：本解析器不做权限校验，权限校验由调用方负责
    """

    def __init__(self, allow_list: List[str]):
        self.allow_list = [os.path.abspath(p) for p in allow_list]
        self._user_home = self._get_user_home()

    def _get_user_home(self) -> str:
        """获取用户主目录"""
        return os.path.expanduser("~")

    def resolve(self, input_path: str, workspace_root: str) -> Tuple[Optional[str], Optional[str]]:
        """
        智能路径解析（仅解析路径，不做权限校验）

        功能：
        1. 处理语义路径（~、desktop、documents 等）
        2. 统一路径分隔符
        3. 支持绝对路径和相对路径
        4. 始终返回绝对路径

        参数:
            input_path: 相对路径或绝对路径
            workspace_root: 工作区根目录

        返回:
            (解析后的绝对路径, 错误信息或None)
            - 成功时返回绝对路径
            - 失败时返回错误信息
        """
        if not input_path or not input_path.strip():
            return None, "路径不能为空"

        original_path = input_path.strip()
        path = original_path

        # 统一路径分隔符
        path = path.replace("/", os.sep).replace("\\", os.sep)

        # 展开家目录
        if path.startswith("~"):
            path = os.path.expanduser(path)

        # 展开环境变量（如 %USERPROFILE%, %APPDATA% 等）
        path = os.path.expandvars(path)

        abs_workspace = os.path.abspath(workspace_root)

        # 如果是绝对路径，直接返回
        if os.path.isabs(path):
            return os.path.abspath(path), None

        # 相对路径，拼接工作区根目录
        abs_path = os.path.abspath(os.path.join(abs_workspace, path))
        return abs_path, None

    def normalize_path(self, path: str) -> str:
        """规范化路径（处理 ~、环境变量等）"""
        path = path.strip()

        path = path.replace("~", self._user_home)

        path = os.path.expandvars(path)

        path = os.path.normpath(path)

        return path

    def is_path_safe(self, path: str) -> bool:
        """检查路径是否安全（不包含危险字符）"""
        dangerous_patterns = ["..", "$", "`", "&&", "|", ";"]
        path_lower = path.lower()
        for pattern in dangerous_patterns:
            if pattern in path_lower:
                return False
        return True
