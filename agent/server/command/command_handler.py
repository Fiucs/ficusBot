#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
命令处理器模块

功能说明:
    - 命令解析和执行
    - 命令注册机制
    - 内置命令实现

核心方法:
    - handle: 解析并执行命令
    - register: 注册新命令
    - get_help: 获取帮助信息

内置命令:
    /help           - 显示帮助
    /new            - 创建新会话
    /sessions       - 显示会话列表
    /session <n>    - 切换会话
    /clear          - 清空上下文
    /models         - 显示模型列表
    /switch <model> - 切换模型
    /reload         - 重载配置
"""
import re
from typing import Callable, Dict, List, Optional, Any, TYPE_CHECKING
from dataclasses import dataclass
from loguru import logger

from .command_context import CommandContext
from .command_result import CommandResult

if TYPE_CHECKING:
    from agent.registry import AgentRegistry
    from agent.main import Agent


@dataclass
class CommandInfo:
    """
    命令信息
    
    Attributes:
        name: 命令名称（不含 /）
        description: 命令描述
        handler: 命令处理函数
        usage: 使用说明
    """
    name: str
    description: str
    handler: Callable
    usage: str = ""


class CommandHandler:
    """
    命令处理器
    
    处理 Bot 模式下的命令，支持命令注册和执行。
    
    功能说明:
        - 命令解析和执行
        - 命令注册机制
        - 内置命令实现
    
    核心方法:
        - handle: 解析并执行命令
        - register: 注册新命令
        - get_help: 获取帮助信息
    
    内置命令:
        /help           - 显示帮助
        /new            - 创建新会话
        /sessions       - 显示会话列表
        /session <n>    - 切换会话
        /clear          - 清空上下文
        /models         - 显示模型列表
        /switch <model> - 切换模型
        /reload         - 重载配置
    
    使用示例:
        from agent.server.command import CommandHandler, CommandContext
        from agent.registry import AGENT_REGISTRY
        
        handler = CommandHandler(AGENT_REGISTRY)
        
        context = CommandContext(
            agent_id="default",
            session_id="sess_xxx",
            chat_id="feishu:ou_xxx"
        )
        
        result = handler.handle("/help", context)
        if result.is_command:
            print(result.message)
    """
    
    COMMAND_PATTERN = re.compile(r'^/(\w+)(?:\s+(.*))?$')
    
    def __init__(self, agent_registry: "AgentRegistry" = None):
        """
        初始化命令处理器。
        
        Args:
            agent_registry: Agent 注册中心实例
        """
        self._registry = agent_registry
        self._commands: Dict[str, CommandInfo] = {}
        self._register_builtin_commands()
    
    def _register_builtin_commands(self):
        """注册内置命令"""
        self.register("help", self._cmd_help, "显示帮助信息", "/help")
        self.register("new", self._cmd_new, "创建新会话", "/new")
        self.register("sessions", self._cmd_sessions, "显示会话列表", "/sessions")
        self.register("session", self._cmd_session, "切换会话", "/session <序号>")
        self.register("clear", self._cmd_clear, "清空对话上下文", "/clear")
        self.register("models", self._cmd_models, "显示可用模型列表", "/models")
        self.register("switch", self._cmd_switch, "切换模型", "/switch <模型名>")
        self.register("reload", self._cmd_reload, "重载配置", "/reload")
    
    def register(
        self, 
        name: str, 
        handler: Callable, 
        description: str = "",
        usage: str = ""
    ) -> None:
        """
        注册命令。
        
        Args:
            name: 命令名称（不含 /）
            handler: 命令处理函数，签名: (args: str, context: CommandContext) -> CommandResult
            description: 命令描述
            usage: 使用说明
        """
        self._commands[name] = CommandInfo(
            name=name,
            description=description,
            handler=handler,
            usage=usage
        )
        logger.debug(f"[CommandHandler] 注册命令: /{name}")
    
    def handle(self, content: str, context: CommandContext) -> CommandResult:
        """
        处理输入内容。
        
        如果是命令则执行并返回结果，否则返回 is_command=False。
        
        Args:
            content: 用户输入内容
            context: 命令上下文
        
        Returns:
            CommandResult: 命令执行结果
        """
        content = content.strip()
        match = self.COMMAND_PATTERN.match(content)
        
        if not match:
            return CommandResult.not_a_command()
        
        cmd_name = match.group(1).lower()
        args = match.group(2) or ""
        
        if cmd_name not in self._commands:
            return CommandResult.error_result(f"未知命令: /{cmd_name}\n输入 /help 查看可用命令")
        
        cmd_info = self._commands[cmd_name]
        
        try:
            result = cmd_info.handler(args, context)
            logger.debug(f"[CommandHandler] 执行命令: /{cmd_name}, 成功: {result.success}")
            return result
        except Exception as e:
            logger.error(f"[CommandHandler] 命令执行失败: /{cmd_name}, 错误: {e}")
            return CommandResult.error_result(f"命令执行失败: {e}")
    
    def get_help(self) -> str:
        """
        获取帮助信息。
        
        Returns:
            str: 格式化的帮助文本
        """
        lines = ["📖 可用命令列表:", ""]
        
        for cmd_info in self._commands.values():
            desc = cmd_info.description or "无描述"
            usage = f"  用法: {cmd_info.usage}" if cmd_info.usage else ""
            lines.append(f"  /{cmd_info.name:<10} - {desc}{usage}")
        
        lines.append("")
        lines.append("💡 提示: 命令不区分大小写")
        
        return "\n".join(lines)
    
    def _get_agent(self, context: CommandContext) -> Optional["Agent"]:
        """获取 Agent 实例"""
        if not self._registry:
            return None
        try:
            return self._registry.get_agent(context.agent_id)
        except Exception:
            return None
    
    def _cmd_help(self, args: str, context: CommandContext) -> CommandResult:
        """处理 /help 命令"""
        return CommandResult.success_result(self.get_help())
    
    def _cmd_new(self, args: str, context: CommandContext) -> CommandResult:
        """处理 /new 命令"""
        agent = self._get_agent(context)
        if not agent:
            return CommandResult.error_result("Agent 未初始化")
        
        new_session_id = agent.conversation.create_new_session()
        
        return CommandResult.success_result(
            f"✅ 已创建新会话\n📋 会话 ID: {new_session_id}",
            new_session_id=new_session_id
        )
    
    def _cmd_sessions(self, args: str, context: CommandContext) -> CommandResult:
        """处理 /sessions 命令"""
        agent = self._get_agent(context)
        if not agent:
            return CommandResult.error_result("Agent 未初始化")
        
        sessions = agent.conversation.list_sessions(limit=20)
        
        if not sessions:
            return CommandResult.success_result("📭 暂无会话记录")
        
        lines = ["📋 会话列表:", ""]
        
        for i, session in enumerate(sessions, 1):
            session_id = session.get("session_id", "")
            metadata = session.get("metadata", {})
            title = metadata.get("title", session_id[:20])
            msg_count = metadata.get("message_count", 0)
            updated = metadata.get("updated_at", "")[:10]
            
            current_marker = "👉 " if session_id == context.session_id else "   "
            lines.append(f"{current_marker}{i}. {title} ({msg_count}条消息, {updated})")
        
        lines.append("")
        lines.append("💡 使用 /session <序号> 切换会话")
        
        return CommandResult.success_result("\n".join(lines), data={"sessions": sessions})
    
    def _cmd_session(self, args: str, context: CommandContext) -> CommandResult:
        """处理 /session 命令"""
        agent = self._get_agent(context)
        if not agent:
            return CommandResult.error_result("Agent 未初始化")
        
        if not args.strip():
            return CommandResult.error_result("请指定会话序号\n用法: /session <序号>")
        
        try:
            index = int(args.strip()) - 1
        except ValueError:
            return CommandResult.error_result("请输入有效的序号数字")
        
        sessions = agent.conversation.list_sessions(limit=20)
        
        if index < 0 or index >= len(sessions):
            return CommandResult.error_result(f"序号超出范围，当前共 {len(sessions)} 个会话")
        
        target_session = sessions[index]
        target_id = target_session.get("session_id")
        
        if target_id == context.session_id:
            return CommandResult.success_result("当前已是该会话")
        
        success = agent.conversation.switch_session(target_id)
        
        if success:
            return CommandResult.success_result(
                f"✅ 已切换到会话\n📋 会话 ID: {target_id}",
                switched_session_id=target_id
            )
        else:
            return CommandResult.error_result("切换会话失败")
    
    def _cmd_clear(self, args: str, context: CommandContext) -> CommandResult:
        """处理 /clear 命令"""
        agent = self._get_agent(context)
        if not agent:
            return CommandResult.error_result("Agent 未初始化")
        
        agent.conversation.clear()
        return CommandResult.success_result("✅ 对话上下文已清空")
    
    def _cmd_models(self, args: str, context: CommandContext) -> CommandResult:
        """处理 /models 命令"""
        from agent.config.configloader import GLOBAL_CONFIG
        
        agent = self._get_agent(context)
        current_model = agent.llm_client.current_model_alias if agent else "未知"
        
        all_models = GLOBAL_CONFIG.list_all_models()
        
        if not all_models:
            return CommandResult.success_result("� 暂无配置任何模型")
        
        lines = ["📋 可用模型列表:", ""]
        
        for full_alias, model_info in all_models.items():
            marker = "👉 " if full_alias == current_model else "   "
            remark = model_info.get("remark", "")
            remark_str = f" - {remark}" if remark else ""
            lines.append(f"{marker}{full_alias}{remark_str}")
        
        lines.append("")
        lines.append(f"📌 当前模型: {current_model}")
        lines.append("💡 使用 /switch <模型名> 切换模型")
        
        models_data = {
            "current_model": current_model,
            "models": [
                {
                    "alias": full_alias,
                    "provider": info.get("provider", ""),
                    "model_name": info.get("model_name", ""),
                    "remark": info.get("remark", ""),
                    "is_current": full_alias == current_model
                }
                for full_alias, info in all_models.items()
            ]
        }
        
        return CommandResult.success_result("\n".join(lines), data=models_data)
    
    def _cmd_switch(self, args: str, context: CommandContext) -> CommandResult:
        """处理 /switch 命令"""
        agent = self._get_agent(context)
        if not agent:
            return CommandResult.error_result("Agent 未初始化")
        
        model_name = args.strip()
        if not model_name:
            return CommandResult.error_result("请指定模型名称\n用法: /switch <模型名>")
        
        from agent.config.configloader import GLOBAL_CONFIG
        all_models = GLOBAL_CONFIG.list_all_models()
        
        if model_name not in all_models:
            available_list = list(all_models.keys())
            return CommandResult.error_result(
                f"模型 '{model_name}' 不在可用列表中\n可用模型: {', '.join(available_list)}"
            )
        
        old_model = agent.llm_client.current_model_alias
        result = agent.llm_client.switch_model(model_name)
        
        if result.get("status") == "error":
            return CommandResult.error_result(result.get("message", "切换模型失败"))
        
        return CommandResult.success_result(
            f"✅ 已切换模型\n📌 {old_model} → {model_name}"
        )
    
    def _cmd_reload(self, args: str, context: CommandContext) -> CommandResult:
        """处理 /reload 命令"""
        from agent.config.configloader import GLOBAL_CONFIG
        
        try:
            GLOBAL_CONFIG.reload()
            
            agent = self._get_agent(context)
            if agent:
                agent.conversation.reload_prompt()
            
            if self._registry:
                self._registry.reload()
            
            return CommandResult.success_result(
                "✅ 配置已重载\n"
                "📌 系统提示词已更新\n"
                "📌 Agent 配置已更新"
            )
        except Exception as e:
            return CommandResult.error_result(f"重载配置失败: {e}")
    
    @property
    def commands(self) -> Dict[str, CommandInfo]:
        """获取所有已注册的命令"""
        return self._commands.copy()
