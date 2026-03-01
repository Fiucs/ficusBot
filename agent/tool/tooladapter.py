# 
# 工具适配器

import os
from typing import Dict, Any, List, Optional
from jsonschema import validate, ValidationError
import json5
from agent.fileSystem.filesystem import FileSystemTool
from agent.skill.skill_loader import SkillLoader
from agent.tool.shelltool import ShellTool


# 
# # 负责将文件操作、shell命令、技能工具等适配为大模型可调用的格式
#
class ToolAdapter:
    def __init__(
        self, 
        file_tool: FileSystemTool, 
        shell_tool: ShellTool, 
        skill_loader: SkillLoader,
        delegation_depth: int = 0
    ):
        self.file_tool = file_tool
        self.shell_tool = shell_tool
        self.skill_loader = skill_loader
        self.delegation_depth = delegation_depth
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
        else:
            raise ValueError(f"未知的工具类型: {tool_type}")

    # 注册所有工具,包括文件操作、shell命令、技能工具
    def _register_all_tools(self):
        # 加载工具配置
        config = self._load_tools_config()
        all_tool_defs = []
        
        # 注册文件工具
        for tool_def in config.get("file_tools", []):
            method_name = tool_def.pop("method")
            tool_def["func"] = self._get_tool_func("file", method_name)
            all_tool_defs.append(tool_def)
        
        # 注册 Shell 工具
        for tool_def in config.get("shell_tools", []):
            method_name = tool_def.pop("method")
            tool_def["func"] = self._get_tool_func("shell", method_name)
            all_tool_defs.append(tool_def)
        
        # 注册技能工具（如果启用）
        skill_config = config.get("skill_tools", {})
        if skill_config.get("enabled", True):
            skill_defs = self.skill_loader.get_skill_tool_definitions()
            for defi in skill_defs:
                func_name = defi["function"]["name"]
                alias = func_name.split(".")[1]
                all_tool_defs.append({
                    "name": func_name,
                    "func": lambda alias=alias, **kwargs: self.skill_loader.execute(alias, kwargs),
                    "description": " ",  # 空白字符，减少 token 消耗。技能描述通过 system prompt 中的技能列表展示
                    "parameters": defi["function"]["parameters"]
                })

        for tool in all_tool_defs:
            self.tools[tool["name"]] = tool

    def list_tools(self) -> List[Dict[str, Any]]:
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
        1. 检查是否为子代理工具（以 "agent." 开头）
        2. 查找工具：从 self.tools 字典中获取工具信息
        3. 参数校验：使用 JSON Schema 验证参数合法性
        4. 执行工具：直接调用 tool_info["func"] 函数对象（非反射）
        
        注意：tool_info["func"] 是在 _register_all_tools() 中预先绑定的函数对象
              - file/shell 工具：通过 _get_tool_func() 获取的方法引用
              - skill 工具：lambda 函数包装器
              
        参数:
            tool_name: 工具名称，如 "file.read", "shell.exec", "skill.xxx", "agent.xxx.delegate"
            arguments: 工具参数字典，如 {"file_path": "test.txt"}
            
        返回:
            工具执行结果字典，包含 status、message 等字段
        """
        if tool_name.startswith("agent."):
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


