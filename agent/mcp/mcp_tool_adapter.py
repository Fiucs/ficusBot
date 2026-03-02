"""
MCP 工具适配器模块

功能说明:
    - 将 MCP 工具适配为 FicusBot 工具格式
    - 与现有 ToolAdapter 无缝集成
    - 提供工具注册和调用接口

工具命名规范:
    - 使用下划线分隔，如 mcp_server_tool（兼容 DeepSeek 等模型）
    - 格式: mcp_{server_name}_{tool_name}

使用示例:
    from agent.mcp import MCPToolAdapter
    
    adapter = MCPToolAdapter(mcp_manager)
    tools = adapter.get_tool_definitions()
    result = adapter.call_tool("mcp_server_tool", {"arg": "value"})
"""

from typing import Dict, Any, List, Optional
from loguru import logger

from .mcp_manager import MCPManager


class MCPToolAdapter:
    """
    MCP 工具适配器
    
    功能说明:
        - 将 MCP 工具转换为 FicusBot 工具格式
        - 提供与 ToolAdapter 一致的接口
        - 支持工具发现和调用
    
    工具命名规范:
        - 使用下划线分隔：mcp_{server_name}_{tool_name}
        - 兼容 DeepSeek 等模型的命名限制
    
    核心方法:
        - get_tool_definitions: 获取工具定义列表
        - call_tool: 调用 MCP 工具
        - list_tools: 列出所有工具
    
    使用示例:
        adapter = MCPToolAdapter(mcp_manager)
        definitions = adapter.get_tool_definitions()
        result = adapter.call_tool("mcp_server_tool", {"arg": "value"})
    """
    
    TOOL_PREFIX = "mcp_"
    
    def __init__(self, mcp_manager: MCPManager):
        """
        初始化 MCP 工具适配器
        
        参数:
            mcp_manager: MCP 管理器实例
        """
        self._manager = mcp_manager
    
    def is_mcp_tool(self, tool_name: str) -> bool:
        """
        检查是否为 MCP 工具
        
        参数:
            tool_name: 工具名称
            
        返回:
            bool: 是否为 MCP 工具
        """
        return tool_name.startswith(self.TOOL_PREFIX)
    
    def parse_tool_name(self, tool_name: str) -> Optional[tuple]:
        """
        解析 MCP 工具名称
        
        参数:
            tool_name: 工具名称，格式为 mcp_server_tool
            
        返回:
            tuple: (server_name, tool_name) 或 None
        """
        if not self.is_mcp_tool(tool_name):
            return None
        
        parts = tool_name[len(self.TOOL_PREFIX):].split("_", 1)
        if len(parts) != 2:
            return None
        
        return (parts[0], parts[1])
    
    def _make_tool_name(self, server_name: str, tool_name: str) -> str:
        """
        生成工具名称
        
        参数:
            server_name: 服务器名称
            tool_name: 工具名称
            
        返回:
            格式化的工具名称: mcp_{server_name}_{tool_name}
        """
        return f"{self.TOOL_PREFIX}{server_name}_{tool_name}"
    
    def get_tool_definitions(self, server_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取工具定义列表
        
        参数:
            server_name: 服务器名称，为 None 时返回所有工具
            
        返回:
            符合 Function Calling 格式的工具定义列表
        """
        return self._manager.get_tool_definitions(server_name)
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用 MCP 工具
        
        参数:
            tool_name: 工具名称，格式为 mcp_server_tool
            arguments: 工具参数
            
        返回:
            工具执行结果
        """
        parsed = self.parse_tool_name(tool_name)
        if not parsed:
            return {
                "status": "error",
                "message": f"无效的 MCP 工具名称: {tool_name}"
            }
        
        server_name, actual_tool_name = parsed
        return self._manager.call_tool_sync(server_name, actual_tool_name, arguments)
    
    def list_tools(self, server_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        列出所有 MCP 工具
        
        参数:
            server_name: 服务器名称，为 None 时返回所有工具
            
        返回:
            工具信息列表
        """
        tools = self._manager.list_tools(server_name)
        return [
            {
                "name": self._make_tool_name(t.server_name, t.name),
                "server": t.server_name,
                "description": t.description,
                "input_schema": t.input_schema
            }
            for t in tools
        ]
    
    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        获取工具详细信息
        
        参数:
            tool_name: 工具名称
            
        返回:
            工具信息字典或 None
        """
        parsed = self.parse_tool_name(tool_name)
        if not parsed:
            return None
        
        server_name, actual_tool_name = parsed
        tools = self._manager.list_tools(server_name)
        
        for tool in tools:
            if tool.name == actual_tool_name:
                return {
                    "name": tool_name,
                    "server": tool.server_name,
                    "description": tool.description,
                    "input_schema": tool.input_schema
                }
        
        return None
    
    def register_to_tool_adapter(self, tool_adapter) -> int:
        """
        将 MCP 工具注册到 ToolAdapter
        
        参数:
            tool_adapter: ToolAdapter 实例
            
        返回:
            注册的工具数量
        """
        count = 0
        tools = self._manager.list_tools()
        
        for tool in tools:
            tool_name = self._make_tool_name(tool.server_name, tool.name)
            
            def make_mcp_caller(server_name, tool_name):
                """
                创建 MCP 工具调用函数。
                
                参数:
                    server_name: MCP 服务器名称
                    tool_name: 工具名称
                    
                返回:
                    调用函数，接受 **kwargs 参数
                """
                def caller(**kwargs):
                    return self.call_tool(self._make_tool_name(server_name, tool_name), kwargs)
                return caller
            
            tool_adapter.tools[tool_name] = {
                "name": tool_name,
                "func": make_mcp_caller(tool.server_name, tool.name),
                "description": tool.description,
                "parameters": tool.input_schema
            }
            count += 1
        
        if count > 0:
            logger.info(f"已注册 {count} 个 MCP 工具到 ToolAdapter")
        
        return count
    
    @property
    def manager(self) -> MCPManager:
        """获取 MCP 管理器"""
        return self._manager
