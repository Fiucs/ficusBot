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
                return self.browser_tool._make_caller(method_name)
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
            all_tool_defs.append({
                "name": "get_skill_document",
                "func": lambda skill_name: self._get_skill_document(skill_name),
                "description": "获取技能的完整文档。当需要使用技能时，先调用此方法获取文档，文档会注入到 system prompt 中。参数: skill_name(必填,技能名称，如 weather, exa-web-search-free)。返回: 技能文档内容。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": "技能名称，从技能列表中选择，如 weather, exa-web-search-free, multi-search-engine"
                        }
                    },
                    "required": ["skill_name"]
                }
            })
        
        for tool_def in config.get("memory_tools", []):
            tool_name = tool_def["name"]
            if tool_name in ["discover", "save_memory", "list_memories"]:
                tool_def["func"] = self._get_memory_tool_func(tool_name)
                all_tool_defs.append(tool_def)
            elif self.memory_system:
                tool_def["func"] = self._get_memory_tool_func(tool_name)
                all_tool_defs.append(tool_def)

        for tool in all_tool_defs:
            self.tools[tool["name"]] = tool
    
    def _get_memory_tool_func(self, tool_name: str):
        """获取记忆系统工具函数"""
        if tool_name == "save_memory":
            return self._save_memory
        elif tool_name == "discover":
            return self._discover
        elif tool_name == "search_memory":
            return self._discover
        elif tool_name == "list_memories":
            return self._list_memories
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
    
    def _list_memories(
        self,
        top_k: int = 10,
        full: bool = True,
        order: str = "desc"
    ) -> Dict[str, Any]:
        """
        列出记忆（不需要搜索关键词）
        
        Args:
            top_k: 返回数量，默认 10
            full: 是否返回完整内容，默认 True
            order: 排序方式，desc(最近的在前) / asc(最早的在前)，默认 desc
        
        Returns:
            {"status": "success", "message": "...", "data": {"total_count": N, "returned_count": M, "memories": [...]}}
        """
        try:
            result = self._run_async(
                self.memory_system.list_memories(top_k, full, order)
            )
            
            total_count = result.get("total_count", 0)
            returned_count = result.get("returned_count", 0)
            
            return {
                "status": "success",
                "message": f"共 {total_count} 条记忆，返回前 {returned_count} 条",
                "data": result
            }
        except Exception as e:
            logger.error(f"列出记忆失败: {e}")
            return {"status": "error", "message": f"列出记忆失败: {str(e)}"}
    
    def _get_skill_document(self, skill_name: str) -> Dict[str, Any]:
        """
        获取技能完整文档（统一入口）
        
        此方法被 get_skill_document 工具调用，返回技能文档供注入 system prompt。
        
        Args:
            skill_name: 技能名称
        
        Returns:
            {"status": "success", "skill_name": xxx, "document": "完整文档", ...}
        """
        return self.skill_loader.get_skill_document(skill_name)
    
    def _register_skill_tool(self, tool_name: str, func_def: Dict[str, Any]) -> bool:
        """
        注册单个技能工具到 self.tools
        
        注意：新架构下，技能通过 get_skill_document 获取文档，
        不再注册单独的技能工具。此方法仅用于返回技能信息。
        
        Args:
            tool_name: 工具名称（如 skill_weather）
            func_def: 工具定义（包含 description、parameters 等）
        
        Returns:
            bool: 始终返回 False（不注册技能工具）
        """
        return False
    
    def _discover(
        self,
        query: str = "",
        resource_type: str = "all",
        top_k: int = 10,
        search_type: str = None,
        distance_threshold: float = None,
        date_range: tuple = None
    ) -> Dict[str, Any]:
        """
        发现可用资源：工具、技能、记忆

        当 resource_type 为 "tool" 或 "all" 时，会搜索记忆索引中的工具和技能。
        对于技能，返回技能名称和文件路径，LLM 需要调用 get_skill_document 获取详细文档。

        Args:
            query: 搜索关键词，为空时返回所有资源
            resource_type: 资源类型 (tool/memory/all)
            top_k: 返回数量
            search_type: 兼容旧参数名，优先使用 resource_type
            distance_threshold: L2 距离阈值，距离越小越相似，默认从配置读取
            date_range: 日期范围过滤（记忆），格式：(start_date, end_date)，如 ("2026-03-01", "2026-03-06")

        Returns:
            {"status": "success", "message": "...", "data": {"tools": [...], "memories": [...], "skills": [...]}}
        """
        if search_type is not None:
            resource_type = search_type

        if distance_threshold is None:
            from agent.config.configloader import GLOBAL_CONFIG
            memory_config = GLOBAL_CONFIG.get("memory", {})
            tool_search_config = memory_config.get("tool_search", {})
            distance_threshold = tool_search_config.get("distance_threshold", 1.0)

        if not query or query.strip() == "":
            logger.debug(f"[发现] 空查询模式，返回所有资源, resource_type={resource_type}, top_k={top_k}")
            distance_threshold = max(distance_threshold * 10, 100.0)
            query = ""

        logger.debug(f"[发现] 开始搜索, query={query}, resource_type={resource_type}, top_k={top_k}, threshold={distance_threshold}")

        try:
            results = self._run_async(
                self.memory_system.search(query, resource_type, top_k, distance_threshold=distance_threshold, date_range=date_range)
            )

            logger.debug(f"[发现] 搜索结果: {len(results.get('tools', []))} 个工具, {len(results.get('memories', []))} 条记忆")

            skills = []
            builtin_tools = []
            filtered_tools = []
            for tool_def in results.get("tools", []):
                func_def = tool_def.get("function", tool_def)
                tool_name = func_def.get("name", "")
                tool_type = func_def.get("tool_type", "builtin")
                if not tool_name:
                    continue

                if tool_type == "skill" or tool_name.startswith("skill_"):
                    skill_name = tool_name[6:] if tool_name.startswith("skill_") else tool_name
                    skill_md_path = func_def.get("skill_md_path", "")
                    capability = func_def.get("capability", "")
                    description = func_def.get("description", "")
                    skills.append({
                        "name": skill_name,
                        "capability": capability,
                        "description": description,
                        "filepath": skill_md_path
                    })
                else:
                    filtered_tools.append(tool_def)
                    if tool_name not in self.tools:
                        builtin_tools.append(tool_name)

            tools_count = len(filtered_tools)
            memories_count = len(results.get("memories", []))
            
            message_parts = []
            if memories_count > 0:
                message_parts.append(f"{memories_count} 条记忆")
            if skills:
                message_parts.append(f"{len(skills)} 个技能（需调用 get_skill_document 获取文档）")
            if builtin_tools:
                message_parts.append(f"{len(builtin_tools)} 个内置工具")
            
            message = f"找到 {', '.join(message_parts)}" if message_parts else "未找到相关内容"
            
            if skills:
                skill_info = "\n".join([f"  - {s['name']}," for s in skills])
                message += f"\n\n发现的技能:\n{skill_info}\n请使用 get_skill_document({{'skill_name': '技能名称'}}) 获取技能文档。"

            logger.info(f"[发现] 搜索结果汇总: query='{query}', 找到 {len(skills)} 个技能, {len(builtin_tools)} 个内置工具, {memories_count} 条记忆")
            logger.debug(f"[发现] 完成: {message}")
            
            return {
                "status": "success",
                "message": message,
                "data": {
                    "tools": filtered_tools,
                    "memories": results.get("memories", []),
                    "skills": skills,
                    "builtin_tools": builtin_tools
                }
            }
        except Exception as e:
            logger.error(f"发现资源失败: {e}")
            return {"status": "error", "message": f"发现资源失败: {str(e)}"}
    
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
        3. 【动态注册】工具不存在时，从记忆系统搜索并注册
        4. 参数校验：使用 JSON Schema 验证参数合法性
        5. 执行工具：直接调用 tool_info["func"] 函数对象（非反射）
        
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
            logger.info(f"[call_tool] 工具 '{tool_name}' 不在当前工具列表中，当前工具数: {len(self.tools)}")
            if self._try_register_tool_from_memory(tool_name):
                logger.info(f"[动态注册] ✓ 工具 '{tool_name}' 已从记忆索引动态注册，当前工具数: {len(self.tools)}")
            else:
                available_tools = list(self.tools.keys())[:10]
                logger.warning(f"[动态注册] ✗ 工具 '{tool_name}' 注册失败，可用工具: {available_tools}...")
                return {"status": "error", "message": f"工具不存在: {tool_name}"}
        else:
            logger.debug(f"[call_tool] 工具 '{tool_name}' 已在工具列表中")
        
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
    
    def _try_register_tool_from_memory(self, tool_name: str) -> bool:
        """
        尝试从记忆系统动态注册工具
        
        当工具不在 self.tools 中时，从记忆索引搜索并动态注册。
        支持技能工具（skill_xxx）和内置工具（file/shell/browser）的按需加载。
        
        Args:
            tool_name: 工具名称
        
        Returns:
            bool: 是否成功注册
        """
        logger.info(f"[动态注册] 开始尝试注册工具: {tool_name}")
        
        if tool_name.startswith("skill_"):
            return self._register_skill_tool_from_memory(tool_name)
        elif tool_name.startswith("browser_"):
            return self._register_builtin_tool_from_config(tool_name, "browser")
        elif tool_name.startswith("file_"):
            return self._register_builtin_tool_from_config(tool_name, "file")
        # elif tool_name.startswith("shell_"):
        #     return self._register_builtin_tool_from_config(tool_name, "shell")
        else:
            logger.debug(f"[动态注册] 未知工具类型，跳过: {tool_name}")
            return False
    
    def _register_skill_tool_from_memory(self, tool_name: str) -> bool:
        """
        从记忆系统注册技能工具
        
        Args:
            tool_name: 工具名称（skill_xxx 格式）
        
        Returns:
            bool: 是否成功注册
        """
        if not self.memory_system:
            logger.warning(f"[动态注册] 记忆系统未启用，无法动态注册技能工具")
            return False
        
        try:
            skill_alias = tool_name[6:]
            logger.info(f"[动态注册] 搜索记忆索引，关键词: {skill_alias}")
            
            tools = self._run_async(
                self.memory_system.search_tools(skill_alias, top_k=1)
            )
            
            if not tools:
                logger.warning(f"[动态注册] 记忆索引中未找到工具: {tool_name}")
                return False
            
            tool_def = tools[0]
            func_def = tool_def.get("function", tool_def)
            found_tool_name = func_def.get("name")
            
            logger.info(f"[动态注册] 搜索结果: {found_tool_name}")
            
            if found_tool_name != tool_name:
                logger.warning(f"[动态注册] 搜索结果不匹配: 期望 {tool_name}, 实际 {found_tool_name}")
                return False
            
            if self._register_skill_tool(tool_name, func_def):
                logger.info(f"[动态注册] ✓ 成功注册技能工具: {tool_name}, 当前工具总数: {len(self.tools)}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"[动态注册] 注册技能工具失败: {tool_name}, 错误: {e}")
            return False
    
    def _register_builtin_tool_from_config(self, tool_name: str, tool_type: str) -> bool:
        """
        从配置文件注册内置工具
        
        Args:
            tool_name: 工具名称
            tool_type: 工具类型（file/shell/browser）
        
        Returns:
            bool: 是否成功注册
        """
        try:
            config = self._load_tools_config()
            tool_list_key = f"{tool_type}_tools"
            tool_defs = config.get(tool_list_key, [])
            
            for tool_def in tool_defs:
                if tool_def.get("name") == tool_name:
                    method_name = tool_def.get("method")
                    if not method_name:
                        logger.warning(f"[动态注册] 工具定义缺少 method 字段: {tool_name}")
                        return False
                    
                    tool_def_copy = tool_def.copy()
                    tool_def_copy.pop("method", None)
                    tool_def_copy["func"] = self._get_tool_func(tool_type, method_name)
                    
                    self.tools[tool_name] = tool_def_copy
                    logger.info(f"[动态注册] ✓ 成功注册内置工具: {tool_name}, 当前工具总数: {len(self.tools)}")
                    return True
            
            logger.warning(f"[动态注册] 配置文件中未找到工具: {tool_name}")
            return False
            
        except Exception as e:
            logger.error(f"[动态注册] 注册内置工具失败: {tool_name}, 错误: {e}")
            return False
    
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
