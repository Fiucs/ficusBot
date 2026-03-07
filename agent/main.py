#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :main.py
# @Time      :2026/02/21 10:33:37
# @Author    :Ficus

"""
Agent 主模块

该模块提供 Agent 实例获取、启动和 API 应用创建功能。
支持消息层架构，统一消息处理入口。
"""
import re
from typing import Dict, List, Optional

from colorama import Fore, Style, init

from .config.configloader import GLOBAL_CONFIG
from .utils.logger import setup_logger_from_config

init(autoreset=True)

setup_logger_from_config(GLOBAL_CONFIG)


def _init_messaging(agent_ids: Optional[List[str]] = None):
    """
    初始化消息层
    
    功能说明:
        - 创建消息通道
        - 注册 Agent 处理器
        - 支持多 Agent 路由
        - 避免重复订阅
    
    Args:
        agent_ids: 要初始化的 Agent ID 列表，为 None 时只初始化默认 Agent
    """
    from agent.core.messaging import Application, ChatHandler
    from agent.registry import AGENT_REGISTRY
    
    app = Application.with_registry(AGENT_REGISTRY)
    channel = app.initialize()
    
    if agent_ids is None:
        agent_ids = ["default"]
    
    loaded_agents = AGENT_REGISTRY.preload_agents(agent_ids)
    
    existing_subscribers = channel.list_subscribers()
    
    for agent_id, agent in loaded_agents.items():
        if agent_id in existing_subscribers:
            continue
        handler = ChatHandler(agent_id, agent, AGENT_REGISTRY)
        channel.subscribe(
            handler.handle,
            name=agent_id,
            filter_func=lambda msg, aid=agent_id: (
                msg.metadata.get("target_agent") == aid or
                msg.metadata.get("target_agent") is None
            )
        )
    
    return app


def run_cli(agent):
    """命令行交互界面
    
    注意：调用此函数前应先调用 _init_messaging() 初始化消息层
    """
    current_agent_id = agent.agent_id if hasattr(agent, 'agent_id') else "default"
    
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    print(f"{Fore.GREEN}🌳 FicusBot 命令行模式{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}命令帮助:{Style.RESET_ALL}")
    print(f"  /exit, /quit     - 退出程序")
    print(f"  /models         - 显示模型列表")
    print(f"  /switch <模型>  - 切换模型")
    print(f"  /reload         - 重载配置")
    print(f"  /clear          - 清空对话上下文")
    print(f"  /sessions       - 显示会话列表")
    print(f"  /session <序号> - 切换会话")
    print(f"  /new            - 创建新会话")
    print(f"  /agents         - 显示可用 Agent 列表")
    print(f"  /agent <id>     - 切换到指定 Agent")
    print(f"  /help           - 显示帮助")
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    print()
    
    current_agent_id = "default"
    
    while True:
        try:
            user_input = input(f"{Fore.CYAN}❯ [{current_agent_id}] {Style.RESET_ALL}").strip()
            if not user_input:
                continue
            
            if user_input in ("/exit", "/quit", "1", "exit", "quit"):
                print(f"{Fore.YELLOW}再见！👋{Style.RESET_ALL}")
                break
            
            if user_input in ("/help"):
                print(f"{Fore.CYAN}命令帮助:{Style.RESET_ALL}")
                print(f"  /exit, /quit     - 退出程序")
                print(f"  /models         - 显示模型列表")
                print(f"  /switch <模型>  - 切换模型")
                print(f"  /reload         - 重载配置")
                print(f"  /clear          - 清空对话上下文")
                print(f"  /sessions       - 显示会话列表")
                print(f"  /session <序号> - 切换会话")
                print(f"  /new            - 创建新会话")
                print(f"  /agents         - 显示可用 Agent 列表")
                print(f"  /agent <id>     - 切换到指定 Agent")
                print(f"  /help           - 显示帮助")
                continue
            
            if user_input in ("/agents"):
                from agent.registry import AGENT_REGISTRY
                agents = AGENT_REGISTRY.list_agents()
                print(f"{Fore.CYAN}可用 Agent 列表:{Style.RESET_ALL}")
                for aid in agents:
                    current = f" {Fore.GREEN}✓ 当前{Style.RESET_ALL}" if aid == current_agent_id else ""
                    config = AGENT_REGISTRY.get_config(aid)
                    desc = config.description if config else ""
                    print(f"  • {aid} - {desc}{current}")
                continue
            
            if user_input.startswith("/agent"):
                parts = user_input.split(maxsplit=1)
                if len(parts) < 2:
                    print(f"{Fore.RED}切换 Agent 格式：/agent <agent_id>{Style.RESET_ALL}")
                    continue
                target_agent_id = parts[1].strip()
                try:
                    agent = get_agent(target_agent_id)
                    current_agent_id = target_agent_id
                    _init_messaging([current_agent_id])
                    print(f"{Fore.GREEN}✓ 已切换到 Agent: {target_agent_id}{Style.RESET_ALL}")
                except ValueError as e:
                    print(f"{Fore.RED}{e}{Style.RESET_ALL}")
                continue
            
            if user_input in ("/models"):
                models = agent.llm_client.list_models()
                print(f"{Fore.CYAN}已配置模型列表:{Style.RESET_ALL}")
                for full_alias, info in models.items():
                    current = f" {Fore.GREEN}✓ 当前{Style.RESET_ALL}" if info["is_current"] else ""
                    print(f"  • {full_alias} - {info['litellm_model']}{current}")
                continue
            
            if user_input in ("/reload"):
                agent.reload()
                print(f"{Fore.GREEN}✓ 配置已重载{Style.RESET_ALL}")
                continue
            
            if user_input in ("/clear"):
                agent.conversation.clear()
                print(f"{Fore.GREEN}✓ 对话上下文已清空{Style.RESET_ALL}")
                continue
            
            if user_input in ("/sessions"):
                sessions = agent.conversation.list_sessions(limit=20)
                if not sessions:
                    print(f"{Fore.YELLOW}暂无会话记录{Style.RESET_ALL}")
                else:
                    print(f"{Fore.CYAN}会话列表:{Style.RESET_ALL}")
                    for i, s in enumerate(sessions, 1):
                        current = f" {Fore.GREEN}【当前】{Style.RESET_ALL}" if s.get("is_current") else ""
                        sid = s["session_id"][-12:]
                        msg = s.get("first_message", "(空会话)")[:30]
                        print(f"  {i}. [{sid}] {msg}{current}")
                continue
            
            if user_input.startswith("/session"):
                parts = user_input.split()
                if len(parts) < 2:
                    print(f"{Fore.RED}切换会话格式：/session <序号>{Style.RESET_ALL}")
                    continue
                try:
                    idx = int(parts[1]) - 1
                    sessions = agent.conversation.list_sessions(limit=20)
                    if idx < 0 or idx >= len(sessions):
                        print(f"{Fore.RED}序号无效{Style.RESET_ALL}")
                        continue
                    target = sessions[idx]["session_id"]
                    if agent.conversation.switch_session(target):
                        print(f"{Fore.GREEN}✓ 已切换到会话: {target[-12:]}{Style.RESET_ALL}")
                    else:
                        print(f"{Fore.RED}会话切换失败{Style.RESET_ALL}")
                except ValueError:
                    print(f"{Fore.RED}请输入有效的序号数字{Style.RESET_ALL}")
                continue
            
            if user_input.startswith("/switch"):
                parts = user_input.split(maxsplit=1)
                if len(parts) < 2:
                    print(f"{Fore.RED}切换模型格式：/switch <厂商/模型别名>{Style.RESET_ALL}")
                    continue
                model_alias = parts[1].strip()
                result = agent.llm_client.switch_model(model_alias)
                print(f"{Fore.GREEN}✓ {result['message']}{Style.RESET_ALL}")
                continue
            
            if user_input in ("/new"):
                new_id = agent.conversation.create_new_session()
                if new_id:
                    print(f"{Fore.GREEN}✓ 新会话已创建: {new_id[-12:]}{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}创建新会话失败{Style.RESET_ALL}")
                continue
            
            print(f"{Fore.CYAN}🤖 思考中...{Style.RESET_ALL}", flush=True)
            
            result = agent.chat(user_input)
            full_content = result.get("content", "")
            
            if full_content:
                plain_text = re.sub(r'\[/?[a-zA-Z][^\]]*\]', '', full_content).strip()
                print(f"🤖 : {plain_text}{Style.RESET_ALL}\n")
                total_tokens = result.get('total_prompt_tokens', 0) + result.get('total_completion_tokens', 0)
                elapsed = result.get('elapsed_time', 0)
                context_window = result.get('context_window', 128000)
                context_usage_percent = result.get('context_usage_percent', 0)
                context_window_display = f"{context_window // 1000}k" if context_window >= 1000 else str(context_window)
                print(f"{Fore.GREEN}✓ 回答完成{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}📊 耗时: {elapsed:.2f}s | 输入: {result.get('total_prompt_tokens', 0)} | 输出: {result.get('total_completion_tokens', 0)} | 总计: {total_tokens}{Style.RESET_ALL}")
                print(f"{Fore.CYAN}📋 上下文: {context_usage_percent:.1f}% of {context_window_display}{Style.RESET_ALL}")
            
        except KeyboardInterrupt:
            break
            
        except Exception as e:
            print(f"{Fore.RED}错误: {str(e)}{Style.RESET_ALL}")


def get_agent(agent_id: str = "default") -> "Agent":
    """
    获取指定 Agent 实例（延迟加载）。
    
    Args:
        agent_id: Agent ID，默认为 "default"
        
    Returns:
        Agent: Agent 实例
    """
    from agent.registry import AGENT_REGISTRY
    return AGENT_REGISTRY.get_agent(agent_id)


def start_agents(agent_ids: Optional[List[str]] = None) -> Dict[str, "Agent"]:
    """
    启动指定的 Agent 实例（批量预加载）。
    
    Args:
        agent_ids: 要启动的 Agent ID 列表，为 None 时启动所有配置的 Agent
        
    Returns:
        Dict[str, Agent]: 已启动的 Agent 实例字典
    """
    from agent.registry import AGENT_REGISTRY
    return AGENT_REGISTRY.preload_agents(agent_ids)


def get_app():
    """
    获取 FastAPI 应用实例（向后兼容）。
    
    返回:
        FastAPI: FastAPI 应用实例
    """
    _init_messaging()
    
    from agent.server.http import create_app
    from agent.server import Gateway
    
    gateway = Gateway()
    return create_app(gateway)


app = None


def _get_app():
    """延迟初始化 app"""
    global app
    if app is None:
        app = get_app()
    return app
