#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
FicusBot TUI 模块

功能说明:
    - 提供基于 Textual 库的终端用户界面
    - 固定底部布局（命令栏+状态栏+输入框）
    - 数字快捷键命令
    - 消息滚动显示

模块导出:
    - run_tui: 启动 TUI 的便捷函数
"""

from .tui_manager import run_tui, FicusBotApp

__all__ = ['run_tui', 'FicusBotApp']
