#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
项目入口文件

功能说明:
    - 作为项目启动的入口点
    - 支持启动单个或多个 Agent
    - 支持 CLI 模式和 API 服务模式分离

使用方法:
    python run.py                      # CLI 模式（默认）
    python run.py --api                # API 服务模式
    python run.py --all-agents         # 启动所有 Agent + CLI
    python run.py --api --all-agents   # 启动所有 Agent + API 服务
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.main import get_agent, start_agents, run_cli


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="FicusBot Agent 启动器")
    
    parser.add_argument(
        "--api",
        action="store_true",
        help="启动 API 服务模式"
    )
    
    parser.add_argument(
        "--agents",
        nargs="+",
        metavar="AGENT_ID",
        help="启动指定的 Agent（多个用空格分隔）"
    )
    
    parser.add_argument(
        "--all-agents",
        action="store_true",
        help="启动所有配置的 Agent"
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
    
    return parser.parse_args()


def main():
    """主入口"""
    args = parse_args()
    from agent.config.configloader import GLOBAL_CONFIG
    from agent.main import get_app
    import uvicorn
    # 在最开始设置 CLAWHUB_WORKDIR
    from agent.config.configloader import GLOBAL_CONFIG
    workspace_root = GLOBAL_CONFIG.get("workspace_root", "./workspace")
    os.environ["CLAWHUB_WORKDIR"] = os.path.abspath(workspace_root)
    
    # 启动指定的 Agent
    if args.all_agents:
        print("🚀 启动所有配置的 Agent...")
        agents = start_agents()
        print(f"✅ 已启动 Agent: {list(agents.keys())}")
    elif args.agents:
        print(f"🚀 启动指定 Agent: {args.agents}")
        agents = start_agents(args.agents)
        print(f"✅ 已启动 Agent: {list(agents.keys())}")
    else:
        agent = get_agent()
    
    host = args.host or GLOBAL_CONFIG.get("api.host", "0.0.0.0")
    port = args.port or GLOBAL_CONFIG.get("api.port", 18080)
    
    # API 服务模式
    if args.api:
        from agent.utils.network import get_local_ip
        
        local_ip = get_local_ip()
        
        print(f"🌐 API 服务已启动:")
        print(f"   • 本地访问: http://127.0.0.1:{port}")
        print(f"   • API 文档: http://127.0.0.1:{port}/docs")
        if local_ip:
            print(f"   • 局域网访问: http://{local_ip}:{port}")
            print(f"   • 局域网文档: http://{local_ip}:{port}/docs")
        
        app = get_app()
        uvicorn.run(app, host=host, port=port)
    else:
        # CLI 模式
        agent = get_agent()
        run_cli(agent)


if __name__ == "__main__":
    main()
