#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :run_bot.py
# @Time      :2026/02/22
# @Author    :Ficus

"""
Bot 网关启动入口

功能说明:
    - 启动机器人网关服务（飞书、Telegram、Discord 等）
    - 支持与 Agent 系统集成
    - 支持 CLI、API 模式同时运行
    - 支持多 Agent 启动

使用方式:
    python run_bot.py                        # 启动 Bot 服务
    python run_bot.py --cli                  # Bot + CLI
    python run_bot.py --api                  # Bot + API
    python run_bot.py --cli --api            # Bot + CLI + API
    python run_bot.py --all-agents           # Bot + 所有 Agent
    python run_bot.py --all-agents --api     # Bot + 所有 Agent + API
    python run_bot.py --agents default coder # Bot + 指定 Agent
    python run_bot.py --echo                 # 回声测试模式
"""

import sys
import os
import asyncio
import argparse
import threading

import nest_asyncio
nest_asyncio.apply()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from colorama import init, Fore, Style
init(autoreset=True)

from agent.config.configloader import GLOBAL_CONFIG
from agent.utils.logger import setup_logger_from_config

setup_logger_from_config(GLOBAL_CONFIG)

from loguru import logger


def print_banner():
    """
    打印启动横幅
    
    显示 FicusBot Gateway 的 ASCII 艺术标题
    """
    banner = f"""
{Fore.CYAN}╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   {Fore.GREEN}🌳 FicusBot Gateway{Fore.CYAN} - 多平台机器人网关                    ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}
"""
    print(banner)


def print_config_info():
    """
    打印配置信息
    
    显示已配置的平台及其启用状态
    """
    channels = GLOBAL_CONFIG.get("bot.channels", {})
    
    print(f"{Fore.CYAN}{'─' * 60}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}📋 已配置的平台:{Style.RESET_ALL}")
    
    enabled_count = 0
    for platform, config in channels.items():
        enabled = config.get("enabled", False)
        status = f"{Fore.GREEN}✓ 启用{Style.RESET_ALL}" if enabled else f"{Fore.RED}✗ 禁用{Style.RESET_ALL}"
        print(f"  • {platform}: {status}")
        if enabled:
            enabled_count += 1
    
    print(f"{Fore.CYAN}{'─' * 60}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}共 {enabled_count} 个平台已启用{Style.RESET_ALL}")
    print()


def start_api_server(host: str, port: int):
    """
    在后台线程启动 API 服务
    
    Args:
        host: API 服务监听主机
        port: API 服务监听端口
    """
    import uvicorn
    from agent.main import app
    uvicorn.run(app, host=host, port=port)


async def run_bot(
    use_echo: bool = False, 
    with_cli: bool = False, 
    with_api: bool = False,
    api_host: str = None,
    api_port: int = None,
    all_agents: bool = False,
    agents: list = None
):
    """
    运行 Bot 网关主函数
    
    Args:
        use_echo: 是否使用回声处理器（测试模式，无需 Agent）
        with_cli: 是否同时启动 CLI 模式
        with_api: 是否同时启动 API 服务
        api_host: API 服务主机，为 None 时使用配置文件中的值
        api_port: API 服务端口，为 None 时使用配置文件中的值
        all_agents: 是否启动所有配置的 Agent
        agents: 指定启动的 Agent ID 列表
    """
    from agent.bot import Gateway
    from agent.main import get_agent, start_agents, run_cli
    
    print_banner()
    print_config_info()
    
    # 启动指定的 Agent（多 Agent 模式）
    if all_agents:
        print(f"{Fore.CYAN}🚀 启动所有配置的 Agent...{Style.RESET_ALL}")
        agents_dict = start_agents()
        print(f"{Fore.GREEN}✅ 已启动 Agent: {list(agents_dict.keys())}{Style.RESET_ALL}")
    elif agents:
        print(f"{Fore.CYAN}🚀 启动指定 Agent: {agents}{Style.RESET_ALL}")
        agents_dict = start_agents(agents)
        print(f"{Fore.GREEN}✅ 已启动 Agent: {list(agents_dict.keys())}{Style.RESET_ALL}")
    
    # 初始化 Agent（非回声模式时）
    agent = None
    if not use_echo:
        try:
            agent = get_agent()
            logger.info("[Bot] Agent 已初始化")
        except Exception as e:
            logger.error(f"[Bot] Agent 初始化失败: {e}, 将使用回声模式")
            use_echo = True
    
    # 创建 Bot 网关
    gateway = Gateway(agent=agent, use_echo_processor=use_echo)
    
    # 从配置文件加载平台监听器
    loaded = gateway.load_from_config()
    
    if loaded == 0:
        print(f"{Fore.RED}❌ 没有可用的监听器，请检查配置{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}提示: 在 config.json 的 bot.channels 中启用平台{Style.RESET_ALL}")
        return
    
    # 启动 API 服务（后台线程）
    if with_api:
        host = api_host or GLOBAL_CONFIG.get("api.host", "0.0.0.0")
        port = api_port or GLOBAL_CONFIG.get("api.port", 18080)
        api_thread = threading.Thread(
            target=start_api_server,
            args=(host, port),
            daemon=True
        )
        api_thread.start()
        print(f"{Fore.GREEN}✓ API 服务已启动: http://{host}:{port}{Style.RESET_ALL}")
    
    # 启动 CLI（后台线程）
    if with_cli and agent:
        def run_cli_thread():
            run_cli(agent)
        
        cli_thread = threading.Thread(target=run_cli_thread, daemon=True)
        cli_thread.start()
        print(f"{Fore.GREEN}✓ CLI 模式已启动{Style.RESET_ALL}")
    
    print(f"{Fore.GREEN}🚀 Bot 网关启动中...{Style.RESET_ALL}")
    
    # 运行 Bot 网关主循环
    try:
        await gateway.run_forever()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}正在停止...{Style.RESET_ALL}")
        await gateway.stop()
    except Exception as e:
        logger.error(f"[Bot] 运行异常: {e}")
        await gateway.stop()


def main():
    """
    主入口函数
    
    解析命令行参数并启动 Bot 网关
    """
    parser = argparse.ArgumentParser(
        description="FicusBot 多平台机器人网关",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run_bot.py                        # 启动 Bot 服务
  python run_bot.py --cli                  # Bot + CLI
  python run_bot.py --api                  # Bot + API
  python run_bot.py --cli --api            # Bot + CLI + API
  python run_bot.py --all-agents           # Bot + 所有 Agent
  python run_bot.py --all-agents --api     # Bot + 所有 Agent + API
  python run_bot.py --agents default coder # Bot + 指定 Agent
  python run_bot.py --echo                 # 回声测试模式
        """
    )
    
    parser.add_argument(
        "--cli",
        action="store_true",
        help="同时启动 CLI 模式"
    )
    
    parser.add_argument(
        "--api",
        action="store_true",
        help="同时启动 API 服务"
    )
    
    parser.add_argument(
        "--echo",
        action="store_true",
        help="使用回声处理器（测试模式，无需 Agent）"
    )
    
    parser.add_argument(
        "--all-agents",
        action="store_true",
        help="启动所有配置的 Agent"
    )
    
    parser.add_argument(
        "--agents",
        nargs="+",
        metavar="AGENT_ID",
        help="启动指定的 Agent（多个用空格分隔）"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="API 服务端口（默认使用配置文件中的端口）"
    )
    
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="API 服务主机（默认使用配置文件中的主机）"
    )
    
    args = parser.parse_args()
    
    try:
        asyncio.run(run_bot(
            use_echo=args.echo, 
            with_cli=args.cli,
            with_api=args.api,
            api_host=args.host,
            api_port=args.port,
            all_agents=args.all_agents,
            agents=args.agents
        ))
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}再见！👋{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
