"""
MCP 管理器模块

功能说明:
    - 管理多个 MCP Server 连接
    - 提供统一的工具发现和调用接口
    - 支持动态添加和移除服务器

核心方法:
    - load_servers: 加载所有配置的服务器
    - connect_server: 连接指定服务器
    - disconnect_server: 断开指定服务器
    - list_tools: 获取所有工具列表
    - call_tool: 调用工具
"""

import asyncio
from typing import Dict, Any, List, Optional
from loguru import logger
from colorama import Fore, Style

from .mcp_config import MCPConfig, MCPServerConfig
from .mcp_client import MCPClientBase, MCPClientLocal, MCPClientRemote, create_mcp_client, MCPToolInfo


class MCPManager:
    """
    MCP 管理器
    
    功能说明:
        - 管理多个 MCP Server 的连接和生命周期
        - 提供统一的工具发现和调用接口
        - 支持远程和本地 MCP Server
        - 与现有工具系统无缝集成
    
    核心方法:
        - load_servers: 从配置加载所有服务器
        - connect_server: 连接指定服务器
        - disconnect_server: 断开指定服务器
        - connect_all: 连接所有启用的服务器
        - disconnect_all: 断开所有服务器
        - list_tools: 获取所有工具列表
        - call_tool: 调用 MCP 工具
        - get_tool_definitions: 获取 Function Calling 格式的工具定义
    
    使用示例:
        manager = MCPManager()
        manager.load_servers()
        await manager.connect_all()
        tools = manager.list_tools()
        result = await manager.call_tool("server", "tool", {"arg": "value"})
    """
    
    def __init__(self):
        """初始化 MCP 管理器，从全局配置加载"""
        self._config = MCPConfig()
        self._clients: Dict[str, MCPClientBase] = {}
        self._tools: Dict[str, MCPToolInfo] = {}
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
    
    def _get_event_loop(self) -> asyncio.AbstractEventLoop:
        """获取或创建事件循环"""
        if self._event_loop is None or self._event_loop.is_closed():
            # 总是创建新的事件循环，避免使用已关闭的循环
            self._event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._event_loop)
        return self._event_loop
    
    def _run_async(self, coro):
        """
        同步运行异步协程
        
        参数:
            coro: 异步协程对象
            
        返回:
            协程执行结果
        """
        try:
            loop = self._get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, coro)
                    return future.result()
            else:
                return loop.run_until_complete(coro)
        except RuntimeError as e:
            logger.debug(f"[MCP] 事件循环问题，使用新循环: {e}")
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
    
    def load_servers(self) -> int:
        """
        从配置加载所有服务器
        
        返回:
            int: 加载的服务器数量
        """
        servers = self._config.list_servers(enabled_only=False)
        logger.info(f"{Fore.CYAN}已加载 {len(servers)} 个 MCP 服务器配置{Style.RESET_ALL}")
        return len(servers)
    
    def reload_config(self):
        """重新加载配置"""
        self._config.reload()
        logger.info(f"{Fore.CYAN}MCP 配置已重载{Style.RESET_ALL}")
    
    async def connect_server(self, server_name: str) -> bool:
        """
        连接指定服务器
        
        参数:
            server_name: 服务器名称
            
        返回:
            bool: 连接是否成功
        """
        if server_name in self._clients:
            client = self._clients[server_name]
            if client.is_connected:
                logger.info(f"MCP 服务器 '{server_name}' 已连接")
                return True
        
        server_config = self._config.get_server(server_name)
        if not server_config:
            logger.error(f"MCP 服务器 '{server_name}' 配置不存在")
            return False
        
        if not server_config.enabled:
            logger.warning(f"MCP 服务器 '{server_name}' 未启用")
            return False
        
        client = create_mcp_client(server_config)
        if not client:
            return False
        
        success = await client.connect()
        if success:
            self._clients[server_name] = client
            for tool in client.tools:
                full_name = f"mcp.{server_name}.{tool.name}"
                self._tools[full_name] = tool
            return True
        return False
    
    async def disconnect_server(self, server_name: str) -> bool:
        """
        断开指定服务器
        
        参数:
            server_name: 服务器名称
            
        返回:
            bool: 断开是否成功
        """
        if server_name not in self._clients:
            return True
        
        client = self._clients[server_name]
        success = await client.disconnect()
        
        if success:
            del self._clients[server_name]
            for tool_name in list(self._tools.keys()):
                if tool_name.startswith(f"mcp.{server_name}."):
                    del self._tools[tool_name]
        
        return success
    
    async def connect_all(self) -> Dict[str, bool]:
        """
        连接所有启用的服务器
        
        返回:
            Dict[str, bool]: 服务器名称 -> 连接结果
        """
        results = {}
        servers = self._config.list_servers(enabled_only=True)
        
        for server in servers:
            result = await self.connect_server(server.name)
            results[server.name] = result
        
        success_count = sum(1 for v in results.values() if v)
        logger.info(f"{Fore.CYAN}MCP 服务器连接完成: {success_count}/{len(results)} 成功{Style.RESET_ALL}")
        
        return results
    
    async def disconnect_all(self) -> Dict[str, bool]:
        """
        断开所有服务器
        
        返回:
            Dict[str, bool]: 服务器名称 -> 断开结果
        """
        results = {}
        
        for server_name in list(self._clients.keys()):
            result = await self.disconnect_server(server_name)
            results[server_name] = result
        
        return results
    
    def list_tools(self, server_name: Optional[str] = None) -> List[MCPToolInfo]:
        """
        获取工具列表
        
        参数:
            server_name: 服务器名称，为 None 时返回所有工具
            
        返回:
            MCPToolInfo 列表
        """
        if server_name:
            return [t for t in self._tools.values() if t.server_name == server_name]
        return list(self._tools.values())
    
    def get_tool_definitions(self, server_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取 Function Calling 格式的工具定义
        
        参数:
            server_name: 服务器名称，为 None 时返回所有工具定义
            
        返回:
            工具定义列表
        """
        tools = self.list_tools(server_name)
        return [t.to_function_definition() for t in tools]
    
    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        调用 MCP 工具
        
        参数:
            server_name: 服务器名称
            tool_name: 工具名称
            arguments: 工具参数
            
        返回:
            工具执行结果
        """
        if server_name not in self._clients:
            return {
                "status": "error",
                "message": f"MCP 服务器 '{server_name}' 未连接"
            }
        
        client = self._clients[server_name]
        if not client.is_connected:
            return {
                "status": "error",
                "message": f"MCP 服务器 '{server_name}' 连接已断开"
            }
        
        return await client.call_tool(tool_name, arguments)
    
    def call_tool_sync(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        同步方式调用 MCP 工具
        
        参数:
            server_name: 服务器名称
            tool_name: 工具名称
            arguments: 工具参数
            
        返回:
            工具执行结果
        """
        return self._run_async(self.call_tool(server_name, tool_name, arguments))
    
    def connect_server_sync(self, server_name: str) -> bool:
        """
        同步方式连接服务器
        
        参数:
            server_name: 服务器名称
            
        返回:
            bool: 连接是否成功
        """
        return self._run_async(self.connect_server(server_name))
    
    def disconnect_server_sync(self, server_name: str) -> bool:
        """
        同步方式断开服务器
        
        参数:
            server_name: 服务器名称
            
        返回:
            bool: 断开是否成功
        """
        return self._run_async(self.disconnect_server(server_name))
    
    def connect_all_sync(self) -> Dict[str, bool]:
        """
        同步方式连接所有服务器
        
        返回:
            Dict[str, bool]: 服务器名称 -> 连接结果
        """
        return self._run_async(self.connect_all())
    
    def disconnect_all_sync(self) -> Dict[str, bool]:
        """
        同步方式断开所有服务器
        
        返回:
            Dict[str, bool]: 服务器名称 -> 断开结果
        """
        return self._run_async(self.disconnect_all())
    
    def get_server_status(self, server_name: str) -> Dict[str, Any]:
        """
        获取服务器状态
        
        参数:
            server_name: 服务器名称
            
        返回:
            状态信息字典
        """
        server_config = self._config.get_server(server_name)
        if not server_config:
            return {"status": "not_found", "message": f"服务器 '{server_name}' 不存在"}
        
        client = self._clients.get(server_name)
        if not client:
            return {
                "status": "disconnected",
                "server_name": server_name,
                "server_type": server_config.server_type,
                "enabled": server_config.enabled,
                "tool_count": 0
            }
        
        return {
            "status": "connected" if client.is_connected else "disconnected",
            "server_name": server_name,
            "server_type": server_config.server_type,
            "enabled": server_config.enabled,
            "tool_count": len(client.tools)
        }
    
    def list_server_status(self) -> List[Dict[str, Any]]:
        """
        获取所有服务器状态
        
        返回:
            状态信息列表
        """
        servers = self._config.list_servers(enabled_only=False)
        return [self.get_server_status(s.name) for s in servers]
    
    @property
    def connected_count(self) -> int:
        """已连接的服务器数量"""
        return sum(1 for c in self._clients.values() if c.is_connected)
    
    @property
    def tool_count(self) -> int:
        """可用工具数量"""
        return len(self._tools)
    
    @property
    def config(self) -> MCPConfig:
        """获取配置对象"""
        return self._config
