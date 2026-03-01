#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
FicusBot TUI 模块

功能说明:
    - 基于 Textual 库的终端用户界面
    - 固定底部布局（命令栏+状态栏+输入框）
    - 数字快捷键切换命令
    - 消息区域可滚动显示
    - 日志信息显示到对话框

核心类:
    - FicusBotApp: Textual 应用主类
"""

import os
import sys
import json
import asyncio
import threading
from typing import Optional, List, Tuple
from datetime import datetime
from queue import Queue

try:
    from textual.app import App, ComposeResult
    from textual.widgets import Static, Input, Footer, RichLog
    from textual.containers import Container, Horizontal, Vertical
    from textual.binding import Binding
    from textual.reactive import reactive
    from textual.scroll_view import ScrollView
    from textual.message import Message
except ImportError as e:
    print(f"缺少依赖库: {e}")
    print("请运行: pip install textual")
    sys.exit(1)

from loguru import logger


COMMANDS = [
    {"key": "1", "cmd": "/exit", "desc": "退出"},
    {"key": "2", "cmd": "/models", "desc": "模型列表"},
    {"key": "3", "cmd": "/switch", "desc": "切换模型"},
    {"key": "4", "cmd": "/reload", "desc": "重载配置"},
    {"key": "5", "cmd": "/clear", "desc": "清空上下文"},
    {"key": "6", "cmd": "/sessions", "desc": "会话列表"},
    {"key": "7", "cmd": "/session", "desc": "切换会话"},
    {"key": "8", "cmd": "/new", "desc": "新建会话"},
    {"key": "9", "cmd": "/help", "desc": "帮助"},
]


CSS = """
Screen {
    background: $surface;
    layout: vertical;
}

#message-area {
    height: 1fr;
    min-height: 5;
    border: solid $primary;
    padding: 0 1;
    overflow-y: auto;
}

#command-bar {
    height: auto;
    min-height: 3;
    border: solid $primary;
    padding: 0 1;
    background: $surface-darken-1;
}

#status-bar {
    height: 2;
    min-height: 2;
    border: solid $primary;
    padding: 0 1;
    background: $surface-darken-2;
}

#input-area {
    height: 3;
    min-height: 2;
    padding: 0 1;
    layout: horizontal;
}

#input-prompt {
    width: auto;
    color: $primary;
}

#input-field {
    width: 1fr;
}

.message-user {
    color: $primary;
}

.message-assistant {
    color: $success;
}

.message-system {
    color: $warning;
}

.message-log {
    color: $text-muted;
}

.command-key {
    color: $warning;
    text-style: bold;
}

.command-desc {
    color: $primary;
}

.status-label {
    text-style: bold;
}

.status-value {
    color: $success;
}
"""


class MessageArea(Container):
    """消息显示区域组件。"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._log_widget: Optional[RichLog] = None
    
    def add_message(self, role: str, content: str, msg_type: str = "chat", timestamp: str = None):
        if timestamp is None:
            timestamp = datetime.now().strftime("%H:%M:%S")
        
        if self._log_widget is None:
            return
            
        if msg_type == "log":
            self._log_widget.write(f"[dim]{timestamp} {content}[/dim]")
        elif role == "user":
            preview = content[:300] + "..." if len(content) > 300 else content
            self._log_widget.write(f"[bold cyan]{timestamp} 👤 你:[/bold cyan] {preview}")
        elif role == "assistant":
            preview = content[:300] + "..." if len(content) > 300 else content
            self._log_widget.write(f"[bold green]{timestamp} 🤖 助手:[/bold green] {preview}")
        elif role == "system":
            self._log_widget.write(f"[bold magenta]{timestamp} 📋 系统:[/bold magenta] {content[:150]}")
    
    def clear_messages(self):
        if self._log_widget:
            self._log_widget.clear()
    
    def compose(self) -> ComposeResult:
        self._log_widget = RichLog(id="message-content", highlight=True, markup=True)
        yield self._log_widget


class CommandBar(Static):
    """命令栏组件。"""
    
    model: reactive[str] = reactive("未设置")
    session: reactive[str] = reactive("新会话")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._model = "未设置"
        self._session = "新会话"
    
    def compose(self) -> ComposeResult:
        yield Static(self._build_command_text())
    
    def _build_command_text(self) -> str:
        lines = []
        row = []
        for cmd in COMMANDS:
            item = f"{cmd['key']}. {cmd['desc']}"
            row.append(item)
            if len(row) == 4:
                lines.append("  ".join(row))
                row = []
        if row:
            lines.append("  ".join(row))
        
        lines.append("")
        lines.append(f"模型: {self._model}  |  会话: {self._session}")
        
        return "\n".join(lines)
    
    def update_status(self, model: str, session: str):
        self._model = model
        self._session = session
        self.update(self._build_command_text())


class InputArea(Container):
    """输入区域组件。"""
    
    def compose(self) -> ComposeResult:
        yield Static("❯ ", id="input-prompt")
        yield Input(placeholder="输入消息或命令...", id="input-field")


class ChatMessage(Message):
    """聊天消息事件。"""
    def __init__(self, content: str):
        super().__init__()
        self.content = content


class FicusBotApp(App):
    """
    FicusBot TUI 应用主类。
    
    功能说明:
        - 固定底部布局
        - 数字快捷键命令
        - 消息滚动显示
        - 日志集成
    """
    
    CSS = CSS
    BINDINGS = [
        Binding(str(cmd["key"]), f"cmd_{cmd['key']}", cmd["desc"]) for cmd in COMMANDS
    ]
    
    def __init__(self, agent, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent
        self._thinking = False
    
    def compose(self) -> ComposeResult:
        with Container(id="main-container"):
            yield MessageArea(id="message-area")
            yield CommandBar(id="command-bar")
            yield InputArea(id="input-area")
    
    def on_mount(self) -> None:
        logger.remove()
        self._setup_logger()
        self._update_status()
        input_field = self.query_one("#input-field", Input)
        input_field.focus()
    
    def _setup_logger(self):
        tui_handler = TUILogHandler(self)
        logger.add(tui_handler, format="{message}", level="INFO", enqueue=False)
    
    def _update_status(self):
        try:
            current_model = self.agent.llm_client.current_model_alias or "未设置"
            
            session_id = self.agent.conversation.session_id
            session_short = session_id[-8:] if session_id else "新会话"
            
            command_bar = self.query_one("#command-bar", CommandBar)
            command_bar.update_status(current_model, session_short)
        except Exception as e:
            self._add_message("system", f"[red]更新状态失败: {e}[/red]", "error")
    
    def _add_message(self, role: str, content: str, msg_type: str = "chat"):
        message_area = self.query_one("#message-area", MessageArea)
        message_area.add_message(role, content, msg_type)
    
    def _clear_messages(self):
        message_area = self.query_one("#message-area", MessageArea)
        message_area.clear_messages()
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "input-field":
            user_input = event.value.strip()
            event.input.value = ""
            
            if not user_input:
                return
            
            self._process_input(user_input)
    
    def _process_input(self, user_input: str):
        if user_input in ("1", "/exit", "/quit", "exit", "quit"):
            self.exit()
            return
        
        if user_input == "2" or user_input in ("/models", "models"):
            self._show_models()
            return
        
        if user_input in ("3", "/switch") or user_input.startswith("/switch ") or user_input.startswith("switch "):
            self._handle_switch(user_input)
            return
        
        if user_input in ("4", "/reload", "reload"):
            self._handle_reload()
            return
        
        if user_input in ("5", "/clear", "clear"):
            self._handle_clear()
            return
        
        if user_input in ("6", "/sessions", "sessions"):
            self._show_sessions()
            return
        
        if user_input in ("7", "/session") or user_input.startswith("/session ") or user_input.startswith("session "):
            self._handle_session(user_input)
            return
        
        if user_input in ("8", "/new", "new"):
            self._handle_new()
            return
        
        if user_input in ("9", "/help", "help"):
            self._show_help()
            return
        
        self._handle_chat(user_input)
    
    def action_cmd_1(self):
        self.exit()
    
    def action_cmd_2(self):
        self._show_models()
    
    def action_cmd_3(self):
        self._add_message("system", "[dim]请输入模型别名，例：/switch openai/gpt35[/dim]", "info")
    
    def action_cmd_4(self):
        self._handle_reload()
    
    def action_cmd_5(self):
        self._handle_clear()
    
    def action_cmd_6(self):
        self._show_sessions()
    
    def action_cmd_7(self):
        self._add_message("system", "[dim]请输入会话序号，例：/session 1（先用 \\ [6] 查看列表）[/dim]", "info")
    
    def action_cmd_8(self):
        self._handle_new()
    
    def action_cmd_9(self):
        self._show_help()
    
    def _show_models(self):
        models = self.agent.llm_client.list_models()
        lines = ["[bold]已配置模型列表:[/bold]"]
        for full_alias, info in models.items():
            current_tag = " ✓ 当前" if info["is_current"] else ""
            lines.append(f"  • {full_alias} - {info['litellm_model']}{current_tag}")
        self._add_message("system", "\n".join(lines), "info")
    
    def _show_sessions(self):
        sessions = self.agent.conversation.list_sessions(limit=20)
        if not sessions:
            self._add_message("system", "暂无会话记录", "info")
            return
        lines = ["[bold]会话列表:[/bold]"]
        for i, s in enumerate(sessions, 1):
            current_tag = " 【当前】" if s.get("is_current") else ""
            session_id_short = s["session_id"][-12:]
            first_msg = s.get("first_message", "(空会话)")[:30]
            lines.append(f"  {i}. [{session_id_short}] {first_msg}{current_tag}")
        lines.append("[dim]提示: 使用 /session <序号> 切换会话[/dim]")
        self._add_message("system", "\n".join(lines), "info")
    
    def _show_help(self):
        help_text = """[bold cyan]🌳 FicusBot TUI 使用帮助[/bold cyan]

2[bold]快捷键命令:[/bold]
  \\ [1] 退出程序    \\ [2] 模型列表    \\ [3] 切换模型    \\ [4] 重载配置
  \\ [5] 清空上下文  \\ [6] 会话列表    \\ [7] 切换会话    \\ [8] 新建会话
  \\ [9] 帮助信息

[bold]对话命令:[/bold]
  直接输入文字进行对话
  /switch <模型>  - 切换模型（例：/switch openai/gpt35）
  /session <序号> - 切换会话（先用 \\ [6] 查看列表）"""
        self._add_message("system", help_text, "info")
    
    def _handle_switch(self, user_input: str):
        if user_input == "3" or user_input == "/switch":
            self._add_message("system", "[dim]请输入模型别名，例：/switch openai/gpt35[/dim]", "info")
            return
        parts = user_input.split(maxsplit=1)
        if len(parts) < 2:
            self._add_message("system", "[red]切换模型格式：/switch 厂商/模型别名[/red]", "error")
            return
        model_alias = parts[1].strip()
        result = self.agent.llm_client.switch_model(model_alias)
        self._add_message("system", f"[green]✓ {result['message']}[/green]", "info")
        self._update_status()
    
    def _handle_reload(self):
        self.agent.reload()
        self._add_message("system", "[green]✓ 配置已重载[/green]", "info")
        self._update_status()
    
    def _handle_clear(self):
        self.agent.conversation.clear()
        self._clear_messages()
        self._add_message("system", "[green]✓ 上下文已清空[/green]", "info")
    
    def _handle_session(self, user_input: str):
        if user_input == "7" or user_input == "/session":
            self._add_message("system", "[dim]请输入会话序号，例：/session 1（先用 \\ [6] 查看列表）[/dim]", "info")
            return
        parts = user_input.split(maxsplit=1)
        if len(parts) < 2:
            self._add_message("system", "[red]切换会话格式：/session <序号>[/red]", "error")
            return
        try:
            index = int(parts[1].strip()) - 1
            sessions = self.agent.conversation.list_sessions(limit=20)
            if index < 0 or index >= len(sessions):
                self._add_message("system", "[red]序号无效，请使用 \\ [6] 查看可用会话[/red]", "error")
                return
            target_session = sessions[index]["session_id"]
            if self.agent.conversation.switch_session(target_session):
                self._clear_messages()
                self._add_message("system", f"[green]✓ 已切换到会话: {target_session[-12:]}[/green]", "info")
                self._update_status()
            else:
                self._add_message("system", "[red]会话切换失败[/red]", "error")
        except ValueError:
            self._add_message("system", "[red]请输入有效的序号数字[/red]", "error")
    
    def _handle_new(self):
        new_id = self.agent.conversation.create_new_session()
        if new_id:
            self._clear_messages()
            self._add_message("system", f"[green]✓ 新会话已创建: {new_id[-12:]}[/green]", "info")
            self._update_status()
        else:
            self._add_message("system", "[red]创建新会话失败[/red]", "error")
    
    async def _chat_task(self, user_input: str):
        full_content = ""
        final_stats = {}
        
        async for chunk in self.agent.chat_stream(user_input):
            if chunk.startswith("data: "):
                try:
                    data = json.loads(chunk[6:].strip())
                    if data["type"] == "content":
                        full_content += data["content"]
                    elif data["type"] == "done":
                        full_content = data["content"]
                        final_stats = {
                            'elapsed_time': data.get('elapsed_time', 0),
                            'total_prompt_tokens': data.get('total_prompt_tokens', 0),
                            'total_completion_tokens': data.get('total_completion_tokens', 0)
                        }
                    elif data["type"] == "error":
                        full_content = data['content']
                except:
                    pass
        
        if final_stats:
            full_content = full_content.strip("\n")
            self._add_message("assistant", full_content)
            total_tokens = final_stats['total_prompt_tokens'] + final_stats['total_completion_tokens']
            stats = f"[dim]📊 耗时: {final_stats['elapsed_time']:.2f}s | 输入: {final_stats['total_prompt_tokens']} | 输出: {final_stats['total_completion_tokens']} | 总计: {total_tokens}[/dim]"
            self._add_message("system", stats, "stats")

    def _handle_chat(self, user_input: str):
        self._add_message("user", user_input)
        self.call_after_refresh(lambda: asyncio.create_task(self._chat_task(user_input)))


class TUILogHandler:
    """TUI 日志处理器。"""
    
    def __init__(self, app: FicusBotApp):
        self.app = app
        self._log_widget = None
    
    def _get_log_widget(self):
        """获取 RichLog widget"""
        if self._log_widget is None:
            try:
                message_area = self.app.query_one("#message-area", MessageArea)
                self._log_widget = message_area._log_widget
            except:
                pass
        return self._log_widget
    
    def __call__(self, message):
        """Loguru sink 函数，接收 dict 格式消息，直接写到 RichLog"""
        try:
            text = message.get("text", "").strip()
            if text:
                log_widget = self._get_log_widget()
                if log_widget:
                    self.app.call_later(log_widget.write, text)
        except:
            pass
    
    def write(self, message):
        """兼容文件类 sink 的写入方法"""
        if message and message.strip():
            try:
                log_widget = self._get_log_widget()
                if log_widget:
                    self.app.call_later(log_widget.write, message.strip())
            except:
                pass
    
    def flush(self):
        pass


def run_tui(agent):
    """
    启动 TUI 界面。
    
    参数:
        agent: Agent 实例
    """
    app = FicusBotApp(agent)
    app.run()
