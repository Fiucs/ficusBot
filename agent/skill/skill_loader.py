
import os
import re
import time
from typing import Any, Dict, List, Optional

import frontmatter
from loguru import logger
from agent.config.configloader import GLOBAL_CONFIG


class SkillLoader:
    """
    技能加载器，负责从文件系统加载和管理技能。
    
    功能说明:
        - 从 workspace/skills 目录加载技能定义
        - 解析 SKILL.md 文件中的元数据和内容
        - 提供技能查询和执行接口
        - 支持技能别名映射
    
    核心方法:
        - load_all_skills: 加载所有技能
        - execute: 执行技能（返回技能说明给大模型）
        - get_skill_tool_definitions: 获取技能工具定义列表
    
    配置项:
        - skill_root_dir: 技能根目录，默认为 workspace/skills
    
    技能文件格式:
        每个技能是一个目录，包含 SKILL.md 文件，格式如下:
        ```yaml
        ---
        name: skill-name
        description: 技能描述
        version: 1.0
        author: 作者
        parameters:
          - name: param1
            type: string
            description: 参数说明
            required: true
        ---
        
        ## What I Do
        功能说明...
        
        ## When To Use
        使用场景...
        
        ## Execution Steps
        执行步骤...
        
        ## Examples
        示例...
        ```
    """
    
    def __init__(self):
        workspace_root = GLOBAL_CONFIG.get("workspace_root", "./workspace")
        self.skill_root_dir = os.path.join(workspace_root, "skills")
        self.skills: Dict[str, Dict[str, Any]] = {}
        self.load_all_skills()

    def load_all_skills(self):
        """加载所有技能到内存中。"""
        total_start = time.time()
        self.skills = {}
        if not os.path.exists(self.skill_root_dir):
            os.makedirs(self.skill_root_dir, exist_ok=True)
            print(f"✅ 已创建技能目录：{self.skill_root_dir}")
            return

        loaded_count = 0
        skill_times = []

        list_start = time.time()
        skill_dirs = []
        for skill_dir_name in os.listdir(self.skill_root_dir):
            skill_dir = os.path.join(self.skill_root_dir, skill_dir_name)
            if not os.path.isdir(skill_dir) or skill_dir_name.startswith("."):
                continue
            skill_dirs.append((skill_dir_name, skill_dir))
        list_time = time.time() - list_start
        logger.debug(f"[SkillLoader] 扫描目录耗时: {list_time*1000:.2f}ms")

        for skill_dir_name, skill_dir in skill_dirs:
            skill_start = time.time()
            skill_obj = self._load_single_skill(skill_dir)
            skill_time = time.time() - skill_start
            skill_times.append((skill_dir_name, skill_time))

            if skill_obj:
                self.skills[skill_obj["name"]] = skill_obj
                if skill_obj["alias"] != skill_obj["name"]:
                    self.skills[skill_obj["alias"]] = skill_obj
                loaded_count += 1

        total_time = time.time() - total_start
        logger.debug(f"[SkillLoader] 总耗时: {total_time*1000:.2f}ms, 加载 {loaded_count} 个技能")

        # 按耗时排序显示前5个最慢的技能
        skill_times.sort(key=lambda x: x[1], reverse=True)
        for name, t in skill_times[:5]:
            logger.debug(f"[SkillLoader] 技能 {name} 加载耗时: {t*1000:.2f}ms")

    def _load_single_skill(self, skill_dir: str) -> Optional[Dict[str, Any]]:
        """
        加载单个技能。
        
        Args:
            skill_dir: 技能目录路径
            
        Returns:
            技能对象字典，加载失败返回 None
        """
        skill_name = os.path.basename(skill_dir)
        timings = {"skill": skill_name}
        total_start = time.time()

        try:
            step_start = time.time()
            skill_md_path = os.path.join(skill_dir, "SKILL.md")
            if not os.path.exists(skill_md_path):
                return None
            timings["check_exist"] = (time.time() - step_start) * 1000

            step_start = time.time()
            post = frontmatter.load(skill_md_path)
            meta = post.metadata
            content = post.content
            timings["frontmatter_load"] = (time.time() - step_start) * 1000

            step_start = time.time()
            # name_in_meta = meta.get("name")
            # if name_in_meta is None or str(name_in_meta).strip() != skill_name:
            #     print(f"⚠️  技能加载失败：{skill_dir} 技能名与目录名不一致")
            #     return None

            required_fields = ["name", "description"]
            for field in required_fields:
                if field not in meta:
                    print(f"⚠️  技能加载失败：{skill_dir} 缺少必填字段 {field}")
                    return None
            timings["validate_meta"] = (time.time() - step_start) * 1000

            step_start = time.time()

            def extract_section(section_names: List[str]) -> str:
                for section_name in section_names:
                    pattern = rf"## {section_name}\n(.*?)(?=\n## |\Z)"
                    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
                    if match:
                        return match.group(1).strip()
                return ""

            extract_start = time.time()
            what_i_do = extract_section(["What I Do", "功能说明", "技能介绍"])
            when_to_use = extract_section(["When To Use", "使用场景", "何时使用"])
            execution_steps = extract_section(["Execution Steps", "执行步骤", "执行逻辑", "How It Works"])
            prompt_template = extract_section(["Prompt Template", "提示词模板", "System Prompt"])
            examples = extract_section(["Examples", "示例", "输入输出示例"])
            timings["extract_sections"] = (time.time() - extract_start) * 1000

            step_start = time.time()
            skill_obj = {
                "name": meta["name"],
                "alias": meta.get("alias", meta["name"]),
                "description": meta["description"],
                "version": meta.get("version", "1.0"),
                "author": meta.get("author", ""),
                "requires": meta.get("requires", {}),
                "parameters": meta.get("parameters", meta.get("params", [])),
                "trigger": meta.get("trigger", []),
                "skill_dir": skill_dir,
                "skill_md_path": skill_md_path,
                "what_i_do": what_i_do,
                "when_to_use": when_to_use,
                "execution_steps": execution_steps,
                "prompt_template": prompt_template,
                "examples": examples,
                "full_content": content
            }
            timings["build_obj"] = (time.time() - step_start) * 1000

            total_time = (time.time() - total_start) * 1000
            timings["total"] = total_time

            # 如果总耗时超过 50ms，记录详细耗时
            if total_time > 50:
                logger.debug(f"[SkillLoader] {skill_name} 详细耗时: frontmatter={timings['frontmatter_load']:.1f}ms, "
                             f"extract={timings['extract_sections']:.1f}ms, total={total_time:.1f}ms")

            return skill_obj
        except Exception as e:
            logger.warning(f"技能加载失败：{skill_dir} 错误：{str(e)}")
            return None

    def execute(self, skill_alias: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行技能 - 返回技能详细说明给大模型。
        
        此方法不直接执行技能中的代码块，而是将技能的详细说明返回给大模型，
        让大模型根据 execution_steps 中的指导决定调用哪些具体工具来完成任务。
        
        Args:
            skill_alias: 技能别名或名称
            params: 技能参数字典，用于填充模板中的占位符
            
        Returns:
            包含技能详细说明的字典，结构如下:
            {
                "status": "success",
                "skill_name": 技能名称,
                "description": 技能描述,
                "what_i_do": 功能说明,
                "when_to_use": 使用场景,
                "execution_steps": 执行步骤（大模型根据此决定调用什么工具）,
                "examples": 示例,
                "full_content": 完整技能文档内容,
                "message": 提示信息
            }
            
        使用场景:
            当大模型调用 skill_xxx 工具时，此方法被触发，返回的技能说明
            会被添加到对话历史中，大模型根据说明内容决定后续的工具调用。
        """
        if skill_alias not in self.skills:
            return {"status": "error", "message": f"技能不存在：{skill_alias}"}
        
        skill = self.skills[skill_alias]
        
        try:
            # 模板参数填充函数
            def fill_template(template: str) -> str:
                if not template:
                    return template
                for k, v in params.items():
                    template = template.replace(f"{{{{{k}}}}}", str(v))
                return template

            # 填充模板参数
            filled_steps = fill_template(skill["execution_steps"])
            filled_prompt = fill_template(skill["prompt_template"]) if skill["prompt_template"] else ""

            # 如果关键字段为空，使用备选逻辑
            what_i_do = skill["what_i_do"] if skill["what_i_do"] else skill["description"]
            when_to_use = skill["when_to_use"] if skill["when_to_use"] else "请参考技能描述和文档内容"
            examples = skill["examples"] if skill["examples"] else "请参考完整文档内容中的示例部分"

            # 返回简洁消息，告知大模型技能文档已注入到 system prompt
            # 完整的技能文档内容会通过 _inject_skill_document_from_result 注入到 system prompt
            message = f"""✓ 技能 '{skill['name']}' 已激活。

【重要提醒】
1. 技能文档已注入到 system prompt 的「当前激活技能」部分，请立即阅读
2. 按照文档中的「执行步骤」调用具体工具（如 shell_exec、file_read 等）
3. 技能激活一次即可，文档会保留在 system prompt 中供你随时参考
4. 不要重复调用 skill_{skill['alias']}，直接执行文档中的工具调用
5. 不要等待用户确认，看到文档后立即执行其中的步骤

请参考 system prompt 中的完整文档来完成任务。"""

            # 返回简化信息给大模型（只包含状态，不包含完整文档）
            # 完整文档会通过 _inject_skill_document_from_result 注入到 system prompt
            return {
                "status": "success",
                "skill_name": skill["name"],
                "message": message
            }
        except Exception as e:
            return {"status": "error", "message": f"技能执行失败：{str(e)}"}

    def get_skill_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        获取所有技能的工具定义列表，用于 Function Calling。
        
        Returns:
            技能工具定义列表，每个定义符合 OpenAI Function Calling 格式
        """
        definitions = []
        unique_skills = {skill["name"]: skill for skill in self.skills.values()}
        for skill_name, skill in unique_skills.items():
            properties = {}
            required = []
            for param in skill["parameters"]:
                param_name = param.get("name", param.get("key", f"param_{len(properties)}"))
                properties[param_name] = {
                    "type": param.get("type", "string"),
                    "description": param.get("description", "")
                }
                if param.get("required", False):
                    required.append(param_name)
            if not properties:
                properties = {
                    "query": {
                        "type": "string",
                        "description": "The search query or user input for this skill"
                    }
                }
                required = ["query"]
            definitions.append({
                "type": "function",
                "function": {
                    "name": f"skill_{skill['alias']}",
                    "description": skill["description"],
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required
                    }
                }
            })
        return definitions

    def get_skill_info(self, skill_alias: str) -> Optional[Dict[str, Any]]:
        """
        获取技能详细信息。
        
        Args:
            skill_alias: 技能别名或名称
            
        Returns:
            技能对象字典，不存在返回 None
        """
        return self.skills.get(skill_alias)

    def list_skills(self) -> List[str]:
        """
        获取所有已加载的技能名称列表。
        
        Returns:
            技能名称列表（去重，包含别名）
        """
        return list(self.skills.keys())

    def get_skill_list_info(self, patterns: List[str] = None) -> str:
        """
        获取技能列表信息（用于注入 system prompt）。
        
        Args:
            patterns: 允许的技能模式列表（支持通配符 *），为 None 或 ["*"] 时返回所有技能
        
        返回格式:
            - name: skill-name-1
              description: 技能描述1
            - name: skill-name-2
              description: 技能描述2
        
        Returns:
            str: 格式化的技能列表字符串
        """
        import fnmatch
        
        unique_skills = {skill["name"]: skill for skill in self.skills.values()}
        
        if patterns is not None and "*" not in patterns:
            if not patterns:
                return ""
            filtered_skills = {}
            for skill_name, skill in unique_skills.items():
                for pattern in patterns:
                    if fnmatch.fnmatch(skill_name, pattern):
                        filtered_skills[skill_name] = skill
                        break
            unique_skills = filtered_skills
        
        lines = []
        for skill_name, skill in unique_skills.items():
            description = skill.get("description", "无描述")
            lines.append(f"- name: {skill_name}")
            lines.append(f"  description: {description}")
        
        result = "\n".join(lines)
        logger.info(f"[SkillLoader] 技能列表生成完成，共 {len(unique_skills)} 个技能")
        return result
