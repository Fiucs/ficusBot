#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :tooladapter.py
# @Time      :2026/02/21
# @Author    :Ficus

"""
工具适配器模块

负责将文件操作、Shell命令、技能工具、记忆系统工具等适配为大模型可调用的格式。

核心功能:
    - 注册和管理各类工具（文件、Shell、技能、记忆）
    - 提供统一的工具调用接口
    - 参数校验和错误处理
    - 支持子代理工具委托

工具类型:
    - file: 文件操作工具（FileSystemTool）
    - shell: Shell命令工具（ShellTool）
    - skill: 技能工具（SkillLoader）
    - memory: 记忆系统工具（MemorySystem）
    - browser: 浏览器工具（BrowserTool）
"""

import os
import asyncio
from typing import Dict, Any, List, Optional
from jsonschema import validate, ValidationError
import json5
from loguru import logger

from agent.fileSystem.filesystem import FileSystemTool
from agent.skill.skill_loader import SkillLoader
from agent.tool.shelltool import ShellTool


class ToolAdapter:
    """
    工具适配器
    
    负责将文件操作、Shell命令、技能工具、记忆系统工具等适配为大模型可调用的格式。
    
    核心功能:
        - 注册和管理各类工具（文件、Shell、技能、记忆）
        - 提供统一的工具调用接口
        - 参数校验和错误处理
        - 支持子代理工具委托
    
    Attributes:
        file_tool: 文件系统工具实例
        shell_tool: Shell命令工具实例
        skill_loader: 技能加载器实例
        memory_system: 记忆系统实例（可选）
        browser_tool: 浏览器工具实例（可选）
        delegation_depth: 子代理委托深度
        tools: 已注册的工具字典
    """
    
    def __init__(
        self, 
        file_tool: FileSystemTool, 
        shell_tool: ShellTool, 
        skill_loader: SkillLoader,
        delegation_depth: int = 0,
        memory_system = None,
        browser_tool = None
    ):
        """
        初始化工具适配器
        
        Args:
            file_tool: 文件系统工具实例
            shell_tool: Shell命令工具实例
            skill_loader: 技能加载器实例
            delegation_depth: 子代理委托深度
            memory_system: 记忆系统实例（可选）
            browser_tool: 浏览器工具实例（可选）
        """
        self.file_tool = file_tool
        self.shell_tool = shell_tool
        self.skill_loader = skill_loader
        self.delegation_depth = delegation_depth
        self.memory_system = memory_system
        self.browser_tool = browser_tool
        self.tools: Dict[str, Dict[str, Any]] = {}
        self._register_all_tools()

    def _load_tools_config(self) -> Dict[str, Any]:
        """从 tools.json 加载工具配置（支持 JSON5 格式，允许注释）"""
        config_path = os.path.join(os.path.dirname(__file__), "tools.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json5.load(f)
        except Exception as e:
            raise RuntimeError(f"加载工具配置文件失败: {config_path}, 错误: {e}")

    def _get_tool_func(self, tool_type: str, method_name: str):
        """根据工具类型和方法名获取对应的函数"""
        if tool_type == "file":
            return getattr(self.file_tool, method_name)
        elif tool_type == "shell":
            return getattr(self.shell_tool, method_name)
        elif tool_type == "browser":
            if self.browser_tool:
                return getattr(self.browser_tool, method_name)
            else:
                raise ValueError(f"浏览器工具未启用")
        else:
            raise ValueError(f"未知的工具类型: {tool_type}")

    def _register_all_tools(self):
        """注册所有工具，包括文件操作、Shell命令、技能工具、记忆系统工具"""
        config = self._load_tools_config()
        all_tool_defs = []
        
        for tool_def in config.get("file_tools", []):
            method_name = tool_def.pop("method")
            tool_def["func"] = self._get_tool_func("file", method_name)
            all_tool_defs.append(tool_def)
        
        for tool_def in config.get("shell_tools", []):
            method_name = tool_def.pop("method")
            tool_def["func"] = self._get_tool_func("shell", method_name)
            all_tool_defs.append(tool_def)
        
        if self.browser_tool:
            for tool_def in config.get("browser_tools", []):
                method_name = tool_def.pop("method")
                tool_def["func"] = self._get_tool_func("browser", method_name)
                all_tool_defs.append(tool_def)
        
        skill_config = config.get("skill_tools", {})
        if skill_config.get("enabled", True):
            skill_defs = self.skill_loader.get_skill_tool_definitions()
            for defi in skill_defs:
                func_name = defi["function"]["name"]
                alias = func_name.split("_")[1]
                all_tool_defs.append({
                    "name": func_name,
                    "func": lambda alias=alias, **kwargs: self.skill_loader.execute(alias, kwargs),
                    "description": " ",
                    "parameters": defi["function"]["parameters"]
                })
        
        if self.memory_system:
            for tool_def in config.get("memory_tools", []):
                tool_name = tool_def["name"]
                tool_def["func"] = self._get_memory_tool_func(tool_name)
                all_tool_defs.append(tool_def)

        for tool in all_tool_defs:
            self.tools[tool["name"]] = tool
    
    def _get_memory_tool_func(self, tool_name: str):
        """获取记忆系统工具函数"""
        if tool_name == "save_memory":
            return self._save_memory
        elif tool_name == "search_memory":
            return self._search_memory
        elif tool_name == "delete_memory":
            return self._delete_memory
        elif tool_name == "register_tool":
            return self._register_tool_to_memory
        elif tool_name == "unregister_tool":
            return self._unregister_tool_from_memory
        elif tool_name == "update_tool_config":
            return self._update_tool_config_in_memory
        else:
            raise ValueError(f"未知的记忆工具: {tool_name}")
    
    def _run_async(self, coro):
        """运行异步协程（同步包装器）"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        else:
            return asyncio.run(coro)
    
    def _save_memory(
        self, 
        content: str, 
        memory_type: str = "conversation", 
        importance: int = 5, 
        tags: List[str] = None
    ) -> Dict[str, Any]:
        """保存记忆"""
        try:
            memory_id = self._run_async(
                self.memory_system.save(content, memory_type, importance, tags)
            )
            return {
                "status": "success",
                "message": f"记忆已保存，ID: {memory_id}",
                "data": {"memory_id": memory_id}
            }
        except Exception as e:
            logger.error(f"保存记忆失败: {e}")
            return {"status": "error", "message": f"保存记忆失败: {str(e)}"}
    
    def _search_memory(
        self, 
        query: str, 
        search_type: str = "all", 
        top_k: int = 10
    ) -> Dict[str, Any]:
        """搜索记忆"""
        try:
            results = self._run_async(
                self.memory_system.search(query, search_type, top_k)
            )
            return {
                "status": "success",
                "message": f"找到 {len(results['memories'])} 条记忆, {len(results['tools'])} 个工具",
                "data": results
            }
        except Exception as e:
            logger.error(f"搜索记忆失败: {e}")
            return {"status": "error", "message": f"搜索记忆失败: {str(e)}"}
    
    def _delete_memory(self, memory_id: str) -> Dict[str, Any]:
        """删除记忆"""
        try:
            success = self._run_async(self.memory_system.delete(memory_id))
            if success:
                return {"status": "success", "message": f"记忆已删除: {memory_id}"}
            else:
                return {"status": "error", "message": f"删除记忆失败: {memory_id}"}
        except Exception as e:
            logger.error(f"删除记忆失败: {e}")
            return {"status": "error", "message": f"删除记忆失败: {str(e)}"}
    
    def _register_tool_to_memory(
        self,
        name: str,
        description: str,
        tool_type: str = "skill",
        source: str = "",
        enabled: bool = True,
        add_to_memory: bool = True
    ) -> Dict[str, Any]:
        """注册工具到记忆索引"""
        try:
            result = self._run_async(
                self.memory_system.register_tool(
                    name, description, tool_type, source, enabled, add_to_memory
                )
            )
            return {
                "status": "success",
                "message": f"工具已注册: {name}",
                "data": {"name": name}
            }
        except Exception as e:
            logger.error(f"注册工具失败: {e}")
            return {"status": "error", "message": f"注册工具失败: {str(e)}"}
    
    def _unregister_tool_from_memory(self, name: str) -> Dict[str, Any]:
        """从记忆索引移除工具"""
        try:
            success = self._run_async(self.memory_system.unregister_tool(name))
            if success:
                return {"status": "success", "message": f"工具已移除: {name}"}
            else:
                return {"status": "error", "message": f"移除工具失败: {name}"}
        except Exception as e:
            logger.error(f"移除工具失败: {e}")
            return {"status": "error", "message": f"移除工具失败: {str(e)}"}
    
    def _update_tool_config_in_memory(
        self,
        name: str,
        enabled: bool = None,
        add_to_memory: bool = None
    ) -> Dict[str, Any]:
        """更新工具配置"""
        try:
            success = self.memory_system.update_tool_config(name, enabled, add_to_memory)
            if success:
                return {"status": "success", "message": f"工具配置已更新: {name}"}
            else:
                return {"status": "error", "message": f"更新工具配置失败: {name}"}
        except Exception as e:
            logger.error(f"更新工具配置失败: {e}")
            return {"status": "error", "message": f"更新工具配置失败: {str(e)}"}

    def list_tools(self) -> List[Dict[str, Any]]:
        """
        获取所有已注册工具的列表
        
        Returns:
            工具列表，每项包含 type、function 字段
        """
        tool_list = []
        for tool_name, tool_info in self.tools.items():
            tool_list.append({
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": tool_info["description"],
                    "parameters": tool_info["parameters"]
                }
            })
        return tool_list

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用指定工具
        
        执行流程：
        1. 检查是否为子代理工具（以 "agent_" 开头）
        2. 查找工具：从 self.tools 字典中获取工具信息
        3. 参数校验：使用 JSON Schema 验证参数合法性
        4. 执行工具：直接调用 tool_info["func"] 函数对象（非反射）
        
        注意：tool_info["func"] 是在 _register_all_tools() 中预先绑定的函数对象
              - file/shell 工具：通过 _get_tool_func() 获取的方法引用
              - skill 工具：lambda 函数包装器
              - memory 工具：同步包装器方法
              
        参数:
            tool_name: 工具名称，如 "file_read", "shell_exec", "skill_xxx", "agent_xxx_delegate"
            arguments: 工具参数字典，如 {"file_path": "test.txt"}
            
        返回:
            工具执行结果字典，包含 status、message 等字段
        """
        if tool_name.startswith("agent_"):
            from agent.tool.subagent_tool import SubAgentTool
            subagent_tool = SubAgentTool(self.delegation_depth)
            return subagent_tool.call(tool_name, arguments)
        
        if tool_name not in self.tools:
            return {"status": "error", "message": f"工具不存在: {tool_name}"}
        tool_info = self.tools[tool_name]
        
        try:
            validate(instance=arguments, schema=tool_info["parameters"])
        except ValidationError as e:
            return {"status": "error", "message": f"参数校验失败: {e.message}"}
        
        try:
            result = tool_info["func"](**arguments)
            return result
        except Exception as e:
            return {"status": "error", "message": f"工具执行失败: {str(e)}"}
    
    def search_tools_from_memory(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        从记忆索引搜索工具
        
        Args:
            query: 搜索查询
            top_k: 返回数量
        
        Returns:
            匹配的工具列表
        """
        if not self.memory_system:
            return []
        
        try:
            return self._run_async(self.memory_system.search_tools(query, top_k))
        except Exception as e:
            logger.error(f"搜索工具失败: {e}")
            return []
