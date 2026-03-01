"""
MCP 配置管理模块

功能说明:
    - 从主配置文件 config.json 加载 MCP Server 配置
    - 支持远程和本地 MCP Server 配置
    - 提供配置验证和默认值处理

配置文件格式 (在 config.json 中):
    {
        "mcp": {
            "servers": {
                "server_name": {
                    "type": "remote|local",
                    "url": "https://...",          // 远程服务必填
                    "command": "python",           // 本地服务必填
                    "args": ["-m", "module"],      // 本地服务参数
                    "description": "服务描述",
                    "enabled": true
                }
            }
        }
    }
"""

import os
import json5
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from loguru import logger
from agent.config.configloader import GLOBAL_CONFIG


@dataclass
class MCPServerConfig:
    """
    MCP Server 配置数据类
    
    属性:
        name: 服务器名称
        server_type: 服务器类型 (remote/local)
        url: 远程服务器 URL（远程服务必填）
        command: 本地服务器启动命令（本地服务必填）
        args: 本地服务器启动参数
        env: 环境变量
        description: 服务描述
        enabled: 是否启用
        timeout: 连接超时时间（秒）
    """
    name: str
    server_type: str = "remote"
    url: Optional[str] = None
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    description: str = ""
    enabled: bool = True
    timeout: int = 60
    
    def validate(self) -> bool:
        """
        验证配置是否有效
        
        Returns:
            bool: 配置是否有效
        """
        if self.server_type == "remote":
            if not self.url:
                logger.warning(f"MCP Server '{self.name}': 远程服务缺少 url 配置")
                return False
        elif self.server_type == "local":
            if not self.command:
                logger.warning(f"MCP Server '{self.name}': 本地服务缺少 command 配置")
                return False
        else:
            logger.warning(f"MCP Server '{self.name}': 未知的服务类型 '{self.server_type}'")
            return False
        return True


class MCPConfig:
    """
    MCP 配置管理类
    
    功能说明:
        - 从主配置文件 config.json 加载 MCP Server 配置
        - 管理多个 MCP Server 配置
        - 提供配置查询接口
    
    核心方法:
        - load: 加载配置
        - get_server: 获取指定服务器配置
        - list_servers: 列出所有服务器配置
        - reload: 重新加载配置
    """
    
    def __init__(self):
        """初始化 MCP 配置管理器，从 GLOBAL_CONFIG 读取配置"""
        self._servers: Dict[str, MCPServerConfig] = {}
        self._load()
    
    def _load(self):
        """从 GLOBAL_CONFIG 加载配置"""
        mcp_config = GLOBAL_CONFIG.get("mcp", {})
        servers_data = mcp_config.get("servers", {})
        
        if not servers_data:
            logger.info("MCP 配置为空，将使用默认示例配置")
            servers_data = self._get_default_servers()
        
        self._parse_config(servers_data)
        logger.info(f"已加载 MCP 配置，共 {len(self._servers)} 个服务器")
    
    def _get_default_servers(self) -> Dict[str, Any]:
        """获取默认服务器配置"""
        return {
            "example-remote": {
                "type": "remote",
                "url": "https://mcp.example.com/mcp",
                "description": "示例远程 MCP 服务",
                "enabled": False
            },
            "example-local": {
                "type": "local",
                "command": "python",
                "args": ["-m", "mcp_server_example"],
                "description": "示例本地 MCP 服务",
                "enabled": False
            }
        }
    
    def _parse_config(self, servers_data: Dict[str, Any]):
        """
        解析配置数据
        
        参数:
            servers_data: 服务器配置数据字典
        """
        self._servers = {}
        
        for name, server_data in servers_data.items():
            server_config = MCPServerConfig(
                name=name,
                server_type=server_data.get("type", "remote"),
                url=server_data.get("url"),
                command=server_data.get("command"),
                args=server_data.get("args", []),
                env=server_data.get("env", {}),
                description=server_data.get("description", ""),
                enabled=server_data.get("enabled", True),
                timeout=server_data.get("timeout", 60)
            )
            
            if server_config.validate():
                self._servers[name] = server_config
    
    def reload(self):
        """重新加载配置"""
        GLOBAL_CONFIG.reload()
        self._load()
    
    def get_server(self, name: str) -> Optional[MCPServerConfig]:
        """
        获取指定服务器配置
        
        参数:
            name: 服务器名称
            
        返回:
            MCPServerConfig 或 None
        """
        return self._servers.get(name)
    
    def list_servers(self, enabled_only: bool = True) -> List[MCPServerConfig]:
        """
        列出所有服务器配置
        
        参数:
            enabled_only: 是否只返回启用的服务器
            
        返回:
            MCPServerConfig 列表
        """
        servers = list(self._servers.values())
        if enabled_only:
            servers = [s for s in servers if s.enabled]
        return servers
    
    def get_all_server_names(self) -> List[str]:
        """获取所有服务器名称"""
        return list(self._servers.keys())
