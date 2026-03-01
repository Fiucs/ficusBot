"""
MCP (Model Context Protocol) 模块

功能说明:
    提供 MCP 协议的客户端和管理功能，支持连接远程和本地 MCP Server。

模块组成:
    - mcp_config: MCP 配置管理
    - mcp_client: MCP 客户端封装
    - mcp_manager: MCP 管理器
    - mcp_tool_adapter: MCP 工具适配器

使用示例:
    from agent.mcp import MCPManager
    
    manager = MCPManager()
    manager.load_servers()
    tools = manager.list_tools()
    result = manager.call_tool("server_name", "tool_name", {"arg": "value"})
"""

from .mcp_config import MCPConfig, MCPServerConfig
from .mcp_client import MCPClientBase, MCPClientLocal, MCPClientRemote, MCPToolInfo, create_mcp_client
from .mcp_manager import MCPManager
from .mcp_tool_adapter import MCPToolAdapter

__all__ = [
    "MCPConfig",
    "MCPServerConfig",
    "MCPClientBase",
    "MCPClientLocal",
    "MCPClientRemote",
    "MCPToolInfo",
    "create_mcp_client",
    "MCPManager",
    "MCPToolAdapter"
]
