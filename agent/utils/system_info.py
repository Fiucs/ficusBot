"""
系统信息工具模块。

提供获取和格式化系统信息的功能，用于 Agent 提示词模板注入。
支持获取当前时间、系统平台、工作目录等信息。
"""

from datetime import datetime
from typing import Dict, Any, Optional
import platform
import os


class SystemInfo:
    """
    系统信息获取工具类。

    功能说明:
        - 获取当前日期时间信息
        - 获取操作系统平台信息
        - 获取工作目录等环境信息
        - 格式化输出为提示词可用的字符串

    核心方法:
        - get_current_time: 获取当前时间（多种格式）
        - get_system_summary: 获取系统摘要信息
        - format_for_prompt: 格式化为提示词注入字符串
        - to_dict: 导出为字典格式

    配置项:
        - DEFAULT_TIME_FORMAT: 默认时间格式 "%Y-%m-%d %H:%M:%S"
        - DEFAULT_DATE_FORMAT: 默认日期格式 "%Y-%m-%d"

    使用场景:
        - Agent 提示词模板中的 {INJECTED_SYSTEM_INFO} 占位符替换
        - 需要向 LLM 提供当前时间和系统上下文时
    """

    DEFAULT_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
    DEFAULT_DATE_FORMAT = "%Y-%m-%d"

    def __init__(self):
        """初始化系统信息工具。"""
        self._cached_info: Optional[Dict[str, Any]] = None

    def get_current_time(self, fmt: Optional[str] = None) -> str:
        """
        获取当前时间字符串。

        Args:
            fmt: 时间格式，默认使用 DEFAULT_TIME_FORMAT

        Returns:
            格式化后的当前时间字符串

        示例:
            >>> info = SystemInfo()
            >>> info.get_current_time()
            '2026-03-13 10:30:00'
            >>> info.get_current_time("%Y年%m月%d日 %H时%M分")
            '2026年03月13日 10时30分'
        """
        fmt = fmt or self.DEFAULT_TIME_FORMAT
        return datetime.now().strftime(fmt)

    def get_current_date(self, fmt: Optional[str] = None) -> str:
        """
        获取当前日期字符串。

        Args:
            fmt: 日期格式，默认使用 DEFAULT_DATE_FORMAT

        Returns:
            格式化后的当前日期字符串

        示例:
            >>> info = SystemInfo()
            >>> info.get_current_date()
            '2026-03-13'
        """
        fmt = fmt or self.DEFAULT_DATE_FORMAT
        return datetime.now().strftime(fmt)

    def get_weekday(self) -> str:
        """
        获取当前星期几（中文）。

        Returns:
            中文星期几，如 "星期五"
        """
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        return weekdays[datetime.now().weekday()]

    def get_platform_info(self) -> Dict[str, str]:
        """
        获取操作系统平台信息。

        Returns:
            包含系统信息的字典
        """
        return {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor() or "Unknown",
            "platform": platform.platform(),
        }

    def get_environment_info(self) -> Dict[str, str]:
        """
        获取环境信息。

        Returns:
            包含环境信息的字典
        """
        return {
            "cwd": os.getcwd(),
            "home": os.path.expanduser("~"),
            "user": os.getenv("USERNAME") or os.getenv("USER") or "Unknown",
        }

    def get_system_summary(self) -> Dict[str, Any]:
        """
        获取完整的系统摘要信息。

        Returns:
            包含所有系统信息的字典
        """
        if self._cached_info is None:
            self._cached_info = {
                "time": {
                    "datetime": self.get_current_time(),
                    "date": self.get_current_date(),
                    "weekday": self.get_weekday(),
                    "timestamp": int(datetime.now().timestamp()),
                },
                "platform": self.get_platform_info(),
                "environment": self.get_environment_info(),
            }
        return self._cached_info

    def format_for_prompt(self, include_time: bool = True, include_platform: bool = False) -> str:
        """
        格式化为提示词注入字符串。

        用于替换 Agent 提示词模板中的 {INJECTED_SYSTEM_INFO} 占位符。

        Args:
            include_time: 是否包含时间信息，默认 True
            include_platform: 是否包含平台信息，默认 False

        Returns:
            格式化后的系统信息字符串

        示例:
            >>> info = SystemInfo()
            >>> print(info.format_for_prompt())
            当前时间：2026-03-13 10:30:00（星期五）
        """
        lines = []

        if include_time:
            time_str = self.get_current_time()
            weekday = self.get_weekday()
            lines.append(f"当前时间：{time_str}（{weekday}）")

        if include_platform:
            platform_info = self.get_platform_info()
            env_info = self.get_environment_info()
            lines.append(f"操作系统：{platform_info['system']} {platform_info['release']}")
            lines.append(f"工作目录：{env_info['cwd']}")
            lines.append(f"当前用户：{env_info['user']}")

        return "\n".join(lines) if lines else ""

    def to_dict(self) -> Dict[str, Any]:
        """
        导出为字典格式。

        Returns:
            包含所有系统信息的字典
        """
        return self.get_system_summary()

    def refresh(self) -> "SystemInfo":
        """
        刷新缓存的系统信息（重新获取当前时间）。

        Returns:
            返回自身实例，支持链式调用
        """
        self._cached_info = None
        return self


def get_system_info_text() -> str:
    """
    获取格式化的系统信息文本（便捷函数）。

    Returns:
        格式化的系统信息字符串，可直接用于提示词注入

    示例:
        >>> text = get_system_info_text()
        >>> print(text)
        当前时间：2026-03-13 10:30:00（星期五）
    """
    return SystemInfo().format_for_prompt() +"\n"


def get_full_system_info_text() -> str:
    """
    获取完整的系统信息文本（便捷函数）。

    Returns:
        包含时间和平台信息的完整系统信息字符串

    示例:
        >>> text = get_full_system_info_text()
        >>> print(text)
        当前时间：2026-03-13 10:30:00（星期五）
        操作系统：Windows 10
        工作目录：C:\\Users\\User\\Project
        当前用户：User
    """
    return SystemInfo().format_for_prompt(include_time=True, include_platform=True) +"\n"


if __name__ == "__main__":
    # 测试代码
    info = SystemInfo()

    print("=" * 50)
    print("系统信息工具测试")
    print("=" * 50)

    print("\n【当前时间】")
    print(f"  标准格式: {info.get_current_time()}")
    print(f"  日期格式: {info.get_current_date()}")
    print(f"  中文星期: {info.get_weekday()}")

    print("\n【提示词格式】")
    print(info.format_for_prompt())

    print("\n【完整信息】")
    print(get_full_system_info_text())

    print("\n【字典格式】")
    import json
    print(json.dumps(info.to_dict(), indent=2, ensure_ascii=False))
