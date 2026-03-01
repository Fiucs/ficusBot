"""
MCP 客户端封装模块

功能说明:
    - 封装 MCP Python SDK 的客户端功能
    - 支持 stdio 和 SSE/HTTP 传输
    - 提供统一的工具调用接口

依赖:
    pip install mcp
"""

import asyncio
import os
import sys
from typing import Dict, Any, List, Optional, Callable
from abc import ABC, abstractmethod
from dataclasses import dataclass
from contextlib import AsyncExitStack
from loguru import logger

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    HAS_MCP_SDK = True
except ImportError:
    HAS_MCP_SDK = False
    logger.warning("MCP SDK 未安装，请运行: pip install mcp")


@dataclass
class MCPToolInfo:
    """
    MCP 工具信息数据类
    
    属性:
        name: 工具名称
        description: 工具描述
        input_schema: 输入参数 Schema
        server_name: 所属服务器名称
    """
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_name: str
    
    def to_function_definition(self) -> Dict[str, Any]:
        """
        转换为 Function Calling 格式的工具定义
        
        返回:
            符合 OpenAI Function Calling 格式的工具定义
        """
        return {
            "type": "function",
            "function": {
                "name": f"mcp.{self.server_name}.{self.name}",
                "description": self.description,
                "parameters": self.input_schema
            }
        }


class MCPClientBase(ABC):
    """
    MCP 客户端基类
    
    功能说明:
        - 定义 MCP 客户端的统一接口
        - 提供连接状态管理
        - 定义工具调用抽象方法
    """
    
    def __init__(self, server_name: str):
        """
        初始化客户端
        
        参数:
            server_name: 服务器名称
        """
        self.server_name = server_name
        self._connected = False
        self._tools: List[MCPToolInfo] = []
        self._session: Optional[ClientSession] = None
        self._exit_stack: Optional[AsyncExitStack] = None
    
    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected
    
    @property
    def tools(self) -> List[MCPToolInfo]:
        """获取工具列表"""
        return self._tools
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        连接到 MCP Server
        
        返回:
            bool: 连接是否成功
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> bool:
        """
        断开与 MCP Server 的连接
        
        返回:
            bool: 断开是否成功
        """
        pass
    
    @abstractmethod
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用 MCP 工具
        
        参数:
            tool_name: 工具名称
            arguments: 工具参数
            
        返回:
            工具执行结果
        """
        pass
    
    async def list_tools(self) -> List[MCPToolInfo]:
        """
        获取 MCP Server 提供的工具列表
        
        返回:
            MCPToolInfo 列表
        """
        return self._tools


class MCPClientLocal(MCPClientBase):
    """
    本地 MCP 客户端
    
    功能说明:
        - 通过 stdio 连接本地 MCP Server
        - 启动子进程运行 MCP Server
        - 管理子进程生命周期
    
    使用示例:
        client = MCPClientLocal("my-server", "python", ["-m", "mcp_server"])
        await client.connect()
        result = await client.call_tool("tool_name", {"arg": "value"})
        await client.disconnect()
    """
    
    def __init__(
        self,
        server_name: str,
        command: str,
        args: List[str],
        env: Optional[Dict[str, str]] = None,
        timeout: int = 60
    ):
        """
        初始化本地 MCP 客户端
        
        参数:
            server_name: 服务器名称
            command: 启动命令
            args: 命令参数
            env: 环境变量
            timeout: 超时时间（秒）
        """
        super().__init__(server_name)
        self._command = command
        self._args = args
        self._env = env or {}
        self._timeout = timeout
        self._read_stream = None
        self._write_stream = None
    
    async def connect(self) -> bool:
        """
        连接到本地 MCP Server。
        
        使用 AsyncExitStack 正确管理异步上下文，
        确保 stdio_client 和 ClientSession 的生命周期正确管理。
        """
        if not HAS_MCP_SDK:
            logger.error("MCP SDK 未安装，无法连接")
            return False
        
        try:
            self._exit_stack = AsyncExitStack()
            
            merged_env = os.environ.copy()
            merged_env.update(self._env)
            
            server_params = StdioServerParameters(
                command=self._command,
                args=self._args,
                env=merged_env
            )
            
            self._read_stream, self._write_stream = await self._exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            
            self._session = await self._exit_stack.enter_async_context(
                ClientSession(self._read_stream, self._write_stream)
            )
            
            await self._session.initialize()
            
            await self._refresh_tools()
            
            self._connected = True
            logger.info(f"MCP 本地服务 '{self.server_name}' 已连接，共 {len(self._tools)} 个工具")
            return True
            
        except Exception as e:
            logger.error(f"连接 MCP 本地服务 '{self.server_name}' 失败: {str(e)}")
            self._connected = False
            if self._exit_stack:
                try:
                    await self._exit_stack.aclose()
                except:
                    pass
                self._exit_stack = None
            return False
    
    async def disconnect(self) -> bool:
        """
        断开与本地 MCP Server 的连接。
        
        通过关闭 AsyncExitStack 来正确清理所有异步资源。
        """
        try:
            if self._exit_stack:
                await self._exit_stack.aclose()
                self._exit_stack = None
            
            self._session = None
            self._read_stream = None
            self._write_stream = None
            self._connected = False
            self._tools = []
            
            logger.info(f"MCP 本地服务 '{self.server_name}' 已断开")
            return True
            
        except Exception as e:
            logger.error(f"断开 MCP 本地服务 '{self.server_name}' 失败: {str(e)}")
            return False
    
    async def _refresh_tools(self):
        """
        刷新工具列表。
        
        从 MCP Server 获取可用工具列表并转换为 MCPToolInfo 对象。
        """
        if not self._session:
            return
        
        try:
            result = await self._session.list_tools()
            self._tools = []
            
            for tool in result.tools:
                tool_info = MCPToolInfo(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=tool.inputSchema or {},
                    server_name=self.server_name
                )
                self._tools.append(tool_info)
                
        except Exception as e:
            logger.error(f"获取工具列表失败: {str(e)}")
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用 MCP 工具。
        
        参数:
            tool_name: 工具名称
            arguments: 工具参数字典
            
        返回:
            包含 status、content/message 的结果字典
        """
        if not self._session or not self._connected:
            return {"status": "error", "message": "MCP 服务未连接"}
        
        try:
            result = await self._session.call_tool(tool_name, arguments)
            
            if result.isError:
                error_text = ""
                for content in result.content:
                    if hasattr(content, 'text'):
                        error_text += content.text
                return {"status": "error", "message": error_text or "工具执行失败"}
            
            output = ""
            for content in result.content:
                if hasattr(content, 'text'):
                    output += content.text
            
            return {
                "status": "success",
                "content": output,
                "server": self.server_name,
                "tool": tool_name
            }
            
        except Exception as e:
            return {"status": "error", "message": f"工具调用失败: {str(e)}"}


class MCPClientRemote(MCPClientBase):
    """
    远程 MCP 客户端
    
    功能说明:
        - 通过 HTTP/SSE 连接远程 MCP Server
        - 支持认证和自定义 Headers
        - 处理网络异常和重连
    
    使用示例:
        client = MCPClientRemote("my-server", "https://mcp.example.com/mcp")
        await client.connect()
        result = await client.call_tool("tool_name", {"arg": "value"})
        await client.disconnect()
    """
    
    def __init__(
        self,
        server_name: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 60
    ):
        """
        初始化远程 MCP 客户端
        
        参数:
            server_name: 服务器名称
            url: 远程服务 URL
            headers: 自定义请求头
            timeout: 超时时间（秒）
        """
        super().__init__(server_name)
        self._url = url
        self._headers = headers or {}
        self._timeout = timeout
    
    async def connect(self) -> bool:
        """
        连接到远程 MCP Server。
        
        使用 AsyncExitStack 正确管理 SSE 客户端的异步上下文。
        """
        if not HAS_MCP_SDK:
            logger.error("MCP SDK 未安装，无法连接")
            return False
        
        try:
            from mcp.client.sse import sse_client
            
            self._exit_stack = AsyncExitStack()
            
            self._read_stream, self._write_stream = await self._exit_stack.enter_async_context(
                sse_client(self._url, self._headers)
            )
            
            self._session = await self._exit_stack.enter_async_context(
                ClientSession(self._read_stream, self._write_stream)
            )
            
            await self._session.initialize()
            
            await self._refresh_tools()
            
            self._connected = True
            logger.info(f"MCP 远程服务 '{self.server_name}' 已连接，共 {len(self._tools)} 个工具")
            return True
            
        except Exception as e:
            logger.error(f"连接 MCP 远程服务 '{self.server_name}' 失败: {str(e)}")
            self._connected = False
            if self._exit_stack:
                try:
                    await self._exit_stack.aclose()
                except:
                    pass
                self._exit_stack = None
            return False
    
    async def disconnect(self) -> bool:
        """
        断开与远程 MCP Server 的连接。
        
        通过关闭 AsyncExitStack 来正确清理所有异步资源。
        """
        try:
            if self._exit_stack:
                await self._exit_stack.aclose()
                self._exit_stack = None
            
            self._session = None
            self._connected = False
            self._tools = []
            
            logger.info(f"MCP 远程服务 '{self.server_name}' 已断开")
            return True
            
        except Exception as e:
            logger.error(f"断开 MCP 远程服务 '{self.server_name}' 失败: {str(e)}")
            return False
    
    async def _refresh_tools(self):
        """
        刷新工具列表。
        
        从远程 MCP Server 获取可用工具列表并转换为 MCPToolInfo 对象。
        """
        if not self._session:
            return
        
        try:
            result = await self._session.list_tools()
            self._tools = []
            
            for tool in result.tools:
                tool_info = MCPToolInfo(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=tool.inputSchema or {},
                    server_name=self.server_name
                )
                self._tools.append(tool_info)
                
        except Exception as e:
            logger.error(f"获取工具列表失败: {str(e)}")
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用 MCP 工具。
        
        参数:
            tool_name: 工具名称
            arguments: 工具参数字典
            
        返回:
            包含 status、content/message 的结果字典
        """
        if not self._session or not self._connected:
            return {"status": "error", "message": "MCP 服务未连接"}
        
        try:
            result = await self._session.call_tool(tool_name, arguments)
            
            if result.isError:
                error_text = ""
                for content in result.content:
                    if hasattr(content, 'text'):
                        error_text += content.text
                return {"status": "error", "message": error_text or "工具执行失败"}
            
            output = ""
            for content in result.content:
                if hasattr(content, 'text'):
                    output += content.text
            
            return {
                "status": "success",
                "content": output,
                "server": self.server_name,
                "tool": tool_name
            }
            
        except Exception as e:
            return {"status": "error", "message": f"工具调用失败: {str(e)}"}


def create_mcp_client(server_config) -> Optional[MCPClientBase]:
    """
    工厂函数：根据配置创建 MCP 客户端
    
    参数:
        server_config: MCPServerConfig 配置对象
        
    返回:
        MCPClientBase 实例或 None
    """
    if not HAS_MCP_SDK:
        logger.error("MCP SDK 未安装，无法创建客户端")
        return None
    
    from .mcp_config import MCPServerConfig
    
    if not isinstance(server_config, MCPServerConfig):
        logger.error("无效的服务器配置类型")
        return None
    
    if server_config.server_type == "local":
        return MCPClientLocal(
            server_name=server_config.name,
            command=server_config.command,
            args=server_config.args,
            env=server_config.env,
            timeout=server_config.timeout
        )
    elif server_config.server_type == "remote":
        return MCPClientRemote(
            server_name=server_config.name,
            url=server_config.url,
            timeout=server_config.timeout
        )
    else:
        logger.error(f"未知的服务类型: {server_config.server_type}")
        return None
