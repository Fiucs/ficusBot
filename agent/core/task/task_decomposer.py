#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :task_decomposer.py
# @Time      :2026/03/10
# @Author    :Ficus

"""
任务拆解器 - 意图判断与任务分解

核心功能:
    - 意图判断：判断用户意图是 new_task 还是 continue
    - 任务拆解：将用户任务分解为可执行的原子步骤
    - 两层校验：格式校验 + 依赖关系校验
    - 重试机制：最多 3 次重试

设计原则:
    - 拆解阶段完全禁止接触任何工具
    - 每个步骤必须是单一动作的原子操作
    - 必须从能力标签列表中选择能力标签
    - 步骤之间必须有明确的依赖关系

使用示例:
    >>> decomposer = TaskDecomposer(llm_client, workspace_root)
    >>> result = decomposer.analyze_and_decompose(
    ...     user_task="查询北京天气并保存到桌面",
    ...     ability_tags=["天气查询", "文件写入"],
    ...     pending_task=None
    ... )
    >>> print(result["task_type"])  # "new_task" 或 "continue"
"""

import json
import re
from typing import Dict, List, Optional, Tuple

from loguru import logger
from colorama import Fore, Style


class DecomposeError(Exception):
    """任务拆解异常"""
    pass


class TaskDecomposer:
    """
    任务拆解器
    
    功能说明:
        - 意图判断：判断用户意图（new_task / continue）
        - 任务拆解：将用户任务分解为可执行的原子步骤
        - 两层校验：格式校验 + 依赖关系校验
        - 重试机制：最多 3 次
    
    核心方法:
        - analyze_and_decompose: 统一入口，意图判断 + 任务拆解
        - _build_system_prompt: 构建动态提示词
        - _extract_task_tree: 提取任务树内容
        - _validate_task_tree: 两层校验
    
    配置项:
        - MAX_RETRIES: 最大重试次数，默认 3
    
    task_type 说明:
        - new_task: 用户提出新任务，需要生成新任务树
        - continue: 用户想继续执行未完成任务，使用已有任务树
    """
    
    MAX_RETRIES = 3
    
    def __init__(self, llm_client, workspace_root: str):
        """
        初始化任务拆解器
        
        Args:
            llm_client: LLM 客户端实例
            workspace_root: 工作区根目录
        """
        self.llm_client = llm_client
        self.workspace_root = workspace_root
        logger.info(f"{Fore.CYAN}任务拆解器初始化完成{Style.RESET_ALL}")
    
    def analyze_and_decompose(
        self, 
        user_task: str, 
        ability_tags: List[str],
        pending_task: Optional[Dict] = None
    ) -> Dict:
        """
        意图判断 + 任务拆解（统一入口）
        
        Args:
            user_task: 用户任务描述
            ability_tags: 能力标签列表
            pending_task: 未完成任务信息（可选），包含：
                - task_id: 任务 ID
                - task_goal: 任务目标
                - progress: 执行进度
                - current_step: 当前步骤
                - status: 任务状态
        
        Returns:
            任务树字典，包含以下字段：
                - task_type: 任务类型（new_task / continue）
                - task_goal: 任务目标
                - total_steps: 步骤总数
                - task_tree: 步骤列表
                - prompt_tokens: 拆解阶段输入 token 数
                - completion_tokens: 拆解阶段输出 token 数
        
        Raises:
            DecomposeError: 任务拆解失败（重试次数用尽）
        
        Example:
            >>> result = decomposer.analyze_and_decompose(
            ...     "查询北京天气", ["天气查询"], None
            ... )
            >>> print(result["task_type"])  # "new_task"
        """
        user_task = user_task or ""
        ability_tags = ability_tags or []
        
        total_prompt_tokens = 0
        total_completion_tokens = 0
        
        logger.info(f"{Fore.CYAN}[任务分析] 开始分析任务: {user_task[:50]}...{Style.RESET_ALL}")
        logger.debug(f"{Fore.CYAN}[任务分析] 可用能力标签: {len(ability_tags)} 个{Style.RESET_ALL}")
        
        if pending_task:
            logger.info(f"{Fore.CYAN}[任务分析] 存在未完成任务: {pending_task.get('task_goal', '')}{Style.RESET_ALL}")
        
        messages = self._build_initial_messages(user_task, ability_tags, pending_task)
        
        print(f"\n{Fore.CYAN}{'─'*50}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[请求消息] 发送给 LLM 的消息:{Style.RESET_ALL}")
        for i, msg in enumerate(messages, 1):
            role = msg.get("role", "unknown")
            content = msg.get("content", "") or ""
            content_preview = content[:200] + "..." if len(content) > 200 else content
            print(f"  {Fore.YELLOW}[{i}] {role}:{Style.RESET_ALL}")
            print(f"     {content_preview}")
        print(f"{Fore.CYAN}{'─'*50}{Style.RESET_ALL}")
        
        for attempt in range(self.MAX_RETRIES):
            try:
                logger.debug(f"{Fore.CYAN}[任务分析] 第 {attempt + 1}/{self.MAX_RETRIES} 次尝试{Style.RESET_ALL}")
                
                response = self.llm_client.chat_completion(messages=messages, stream=False)
                
                if hasattr(response, 'usage') and response.usage:
                    total_prompt_tokens += response.usage.prompt_tokens or 0
                    total_completion_tokens += response.usage.completion_tokens or 0
                
                content = response.choices[0].message.content or ""
                
                if not content:
                    messages.append({"role": "assistant", "content": ""})
                    messages.append({"role": "user", "content": "响应内容为空，请重新输出任务树 JSON"})
                    logger.warning(f"{Fore.YELLOW}[任务分析] LLM 响应为空，重试{Style.RESET_ALL}")
                    continue
                
                logger.debug(f"{Fore.CYAN}[任务分析] LLM 响应: {content[:88888]}...{Style.RESET_ALL}")
                
                task_tree_str = self._extract_task_tree(content)
                if not task_tree_str:
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": "必须输出 <task_tree> 包裹的合法任务树 JSON"})
                    logger.warning(f"{Fore.YELLOW}[任务分析] 未找到 <task_tree> 标签，重试{Style.RESET_ALL}")
                    continue
                
                try:
                    task_tree = json.loads(task_tree_str)
                except json.JSONDecodeError as e:
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": f"任务树 JSON 格式非法: {str(e)}，请重新输出"})
                    logger.warning(f"{Fore.YELLOW}[任务分析] JSON 解析失败: {e}，重试{Style.RESET_ALL}")
                    continue
                
                is_valid, error_msg = self._validate_task_tree(task_tree, pending_task)
                if not is_valid:
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": f"校验失败: {error_msg}，请重新输出"})
                    logger.warning(f"{Fore.YELLOW}[任务分析] 校验失败: {error_msg}，重试{Style.RESET_ALL}")
                    continue
                
                task_type = task_tree.get("task_type", "new_task")
                logger.info(f"{Fore.GREEN}[任务分析] 分析成功，task_type: {task_type}{Style.RESET_ALL}")
                
                if task_type == "new_task":
                    logger.debug(f"{Fore.GREEN}[任务分析] 步骤数: {task_tree.get('total_steps', 0)}{Style.RESET_ALL}")
                
                task_tree["prompt_tokens"] = total_prompt_tokens
                task_tree["completion_tokens"] = total_completion_tokens
                
                return task_tree
                
            except Exception as e:
                logger.error(f"{Fore.RED}[任务分析] 第 {attempt + 1} 次尝试失败: {e}{Style.RESET_ALL}")
                if attempt == self.MAX_RETRIES - 1:
                    default_tree = self._create_default_task_tree()
                    default_tree["prompt_tokens"] = total_prompt_tokens
                    default_tree["completion_tokens"] = total_completion_tokens
                    return default_tree
        
        default_tree = self._create_default_task_tree()
        default_tree["prompt_tokens"] = total_prompt_tokens
        default_tree["completion_tokens"] = total_completion_tokens
        return default_tree
    
    def _build_initial_messages(
        self, 
        user_task: str, 
        ability_tags: List[str],
        pending_task: Optional[Dict]
    ) -> List[Dict]:
        """
        构建初始消息列表
        
        Args:
            user_task: 用户任务描述
            ability_tags: 能力标签列表
            pending_task: 未完成任务信息
        
        Returns:
            消息列表
        """
        system_prompt = self._build_system_prompt(ability_tags, pending_task)
        user_prompt = self._build_user_prompt(user_task)
        
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    
    def _build_system_prompt(
        self, 
        ability_tags: List[str],
        pending_task: Optional[Dict]
    ) -> str:
        """
        构建系统提示词（包含意图判断 + 任务拆解）
        
        Args:
            ability_tags: 能力标签列表
            pending_task: 未完成任务信息
        
        Returns:
            系统提示词
        """
        ability_tags_str = "\n".join([f"- {tag}" for tag in ability_tags])
        
        if pending_task:
            status_section = f"""## 当前状态

**存在未完成任务**：
- 任务目标: {pending_task.get('task_goal', '')}
- 执行进度: {pending_task.get('progress', '')}
- 当前步骤: {pending_task.get('current_step', {}).get('step_desc', '无') if pending_task.get('current_step') else '无'}"""
        else:
            status_section = """## 当前状态

**当前没有未完成任务**"""
        
        return f"""# 任务分析系统

## 角色
你是一个任务分析专家，负责判断用户意图并生成任务树。

{status_section}

## 可用能力标签列表
以下是当前可用的能力标签，优先从中选择：

{ability_tags_str}

**特殊能力标签**：
- `llm_response`: 纯 LLM 回答，不需要使用工具

**标签生成规则**：
- 优先从【可用能力标签列表】中选择匹配的标签
- 如果列表中没有合适的标签，可以自行生成描述性标签（如："邮件发送"、"微信通知"、"API调用"）
- 生成的标签应简洁、通用、易于理解

## 最高优先级规则
1. 必须先输出符合规范的任务树 JSON，用 <task_tree> 标签包裹
2. 拆解完成前，绝对禁止：
   - 提及任何工具名称
   - 调用任何工具
   - 执行任何命令
   - 输出自由文本、思考过程
3. 每个步骤必须是单一动作的原子操作
4. 优先从能力标签列表中选择，无匹配时可自行生成描述性标签
5. 步骤之间必须有明确的依赖关系

## 任务树格式规范
<task_tree>
{{
  "task_type": "new_task 或 continue",
  "task_goal": "任务目标一句话描述",
  "total_steps": 步骤数,
  "task_tree": [
    {{
      "step_id": "step_1",
      "step_desc": "原子步骤描述",
      "dependent_on": null,
      "required_abilities": ["能力标签或llm_response"],
      "status": "pending"
    }}
  ]
}}
</task_tree>

## task_type 说明
- `new_task`: 用户提出新任务（生成新任务树）
- `continue`: 用户想继续执行未完成的任务（使用已有任务树）

## 判断原则
1. **继续判断**：用户明确表示要继续、完成、执行未完成任务 → task_type: "continue"
2. **新任务判断**：其他所有情况 → task_type: "new_task"

## 注意事项
- `continue` 类型不需要输出完整任务树，total_steps 可为 0，task_tree 可为空数组
- `new_task` 类型必须输出完整的任务树
- `required_abilities` 从可用能力标签中选择，或使用 `llm_response` 表示纯对话

## 拆解原则

**核心规则：默认合并，只有满足以下条件才拆分**

### 应该拆分的情况（满足其一）：
1. **独立输出操作**：需要读文件，保存文件、发邮件、发微信、调用API等
2. **多目标输出**：需要产生多个独立结果（如：搜索A和B，分别保存）
3. **明确的中断点**：用户明确要求分步骤执行

### 应该合并的情况（默认）：
1. **读取+处理**：读取文件后分析/总结/处理
2. **搜索+回答**：搜索信息后回答问题
3. **分析+输出**：任何分析类任务（统计、检查、遍历等）
4. **纯对话**：问答、解释、翻译等

### 判断公式：
```
是否有独立的输出操作？
├── 是 → 拆分（获取结果 → 输出操作）
└── 否 → 合并为1步

独立输出操作包括：
- 写入文件/数据库
- 发送邮件/微信/短信
- 调用外部API
- 打印/导出
- 其他有独立意义的输出
```

## 字段说明
- `task_type`: 任务类型，必须为 "new_task" 或 "continue"
- `task_goal`: 用户任务的简洁目标描述。注意：必须保留用户的回复偏好（如"简短"、"详细"、"总结"等），但可以省略具体路径、参数等执行细节
- `total_steps`: 步骤总数，必须与 task_tree 数组长度一致
- `step_id`: 步骤唯一标识，格式为 step_数字
- `step_desc`: 步骤描述，具体可执行的动作描述
- `dependent_on`: 依赖的前置步骤 ID，无依赖为 null
- `required_abilities`: 能力标签数组，从能力标签列表中选择
- `status`: 固定为 "pending"

## 示例

**示例 1：需要拆分（有独立输出操作）**
用户任务：查询北京天气并保存到桌面

<task_tree>
{{
  "task_type": "new_task",
  "task_goal": "查询北京天气并保存到桌面",
  "total_steps": 2,
  "task_tree": [
    {{
      "step_id": "step_1",
      "step_desc": "查询北京今天的天气信息",
      "dependent_on": null,
      "required_abilities": ["天气查询"],
      "status": "pending"
    }},
    {{
      "step_id": "step_2",
      "step_desc": "将天气结果写入桌面文件",
      "dependent_on": "step_1",
      "required_abilities": ["文件写入"],
      "status": "pending"
    }}
  ]
}}
</task_tree>

**示例 2：需要合并（无独立输出操作）**
用户任务：读取桌面test.txt文件并总结内容

<task_tree>
{{
  "task_type": "new_task",
  "task_goal": "读取文件并总结内容告知用户",
  "total_steps": 1,
  "task_tree": [
    {{
      "step_id": "step_1",
      "step_desc": "读取桌面test.txt文件内容并总结告知用户",
      "dependent_on": null,
      "required_abilities": ["文件读取", "llm_response"],
      "status": "pending"
    }}
  ]
}}
</task_tree>

**示例 3：继续任务**
用户任务：继续执行

<task_tree>
{{
  "task_type": "continue",
  "task_goal": "继续执行未完成任务",
  "total_steps": 0,
  "task_tree": []
}}
</task_tree>

**重要说明**：
- `required_abilities` 是能力需求标签数组，不是工具名称
- 一个步骤可以需要多个能力（如同时需要"网络搜索"和"文件写入"）
- 执行阶段会根据能力需求动态匹配工具（通过 discover 或能力标签映射）
- 拆解阶段只知道"需要什么能力"，不知道"用什么工具"
"""
    
    def _build_user_prompt(self, user_task: str) -> str:
        """
        构建用户提示词
        
        Args:
            user_task: 用户任务描述
        
        Returns:
            用户提示词
        """
        return f"""## 用户任务

{user_task}

## 工作区信息

- 根目录: {self.workspace_root}
- 操作系统: Windows

请根据上述任务，输出符合规范的任务树 JSON。"""
    
    def _extract_task_tree(self, content: str) -> Optional[str]:
        """
        提取任务树内容
        
        Args:
            content: LLM 响应内容
        
        Returns:
            任务树 JSON 字符串，未找到则返回 None
        """
        match = re.search(r'<task_tree>(.*?)</task_tree>', content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None
    
    def _validate_task_tree(
        self, 
        task_tree: Dict,
        pending_task: Optional[Dict]
    ) -> Tuple[bool, str]:
        """
        两层校验：格式 + 依赖关系
        
        Args:
            task_tree: 任务树字典
            pending_task: 未完成任务信息
        
        Returns:
            (是否通过, 错误信息)
        """
        is_valid, error_msg = self._validate_format(task_tree, pending_task)
        if not is_valid:
            return False, error_msg
        
        task_type = task_tree.get("task_type", "new_task")
        if task_type == "new_task":
            is_valid, error_msg = self._validate_dependencies(task_tree)
            if not is_valid:
                return False, error_msg
        
        return True, ""
    
    def _validate_format(
        self, 
        task_tree: Dict,
        pending_task: Optional[Dict]
    ) -> Tuple[bool, str]:
        """
        第一层：格式校验
        
        Args:
            task_tree: 任务树字典
            pending_task: 未完成任务信息
        
        Returns:
            (是否通过, 错误信息)
        """
        required_fields = ["task_type", "task_goal", "total_steps", "task_tree"]
        for field in required_fields:
            if field not in task_tree:
                return False, f"缺少必需字段: {field}"
        
        task_type = task_tree.get("task_type")
        if task_type not in ["new_task", "continue"]:
            return False, f"task_type 必须为 'new_task' 或 'continue'，当前为: {task_type}"
        
        if task_type == "continue" and not pending_task:
            return False, "task_type 为 'continue' 但没有未完成任务"
        
        if not isinstance(task_tree["task_goal"], str) or not task_tree["task_goal"].strip():
            return False, "task_goal 必须是非空字符串"
        
        if not isinstance(task_tree["total_steps"], int) or task_tree["total_steps"] < 0:
            return False, "total_steps 必须是非负整数"
        
        if not isinstance(task_tree["task_tree"], list):
            return False, "task_tree 必须是数组"
        
        if task_type == "continue":
            return True, ""
        
        if task_tree["total_steps"] != len(task_tree["task_tree"]):
            return False, f"total_steps ({task_tree['total_steps']}) 与 task_tree 长度 ({len(task_tree['task_tree'])}) 不一致"
        
        if len(task_tree["task_tree"]) == 0:
            return False, "new_task 类型的 task_tree 不能为空"
        
        step_ids = set()
        for i, step in enumerate(task_tree["task_tree"], 1):
            step_required_fields = ["step_id", "step_desc", "dependent_on", "status"]
            for field in step_required_fields:
                if field not in step:
                    return False, f"步骤 {i} 缺少必需字段: {field}"
            
            if "required_abilities" not in step and "required_ability" not in step:
                return False, f"步骤 {i} 缺少必需字段: required_abilities 或 required_ability"
            
            if not re.match(r'^step_\d+$', step["step_id"]):
                return False, f"步骤 {i} 的 step_id 格式错误，应为 step_数字"
            
            if step["step_id"] in step_ids:
                return False, f"步骤 ID 重复: {step['step_id']}"
            step_ids.add(step["step_id"])
            
            if not isinstance(step["step_desc"], str) or not step["step_desc"].strip():
                return False, f"步骤 {i} 的 step_desc 必须是非空字符串"
            
            if step["dependent_on"] is not None and not isinstance(step["dependent_on"], str):
                return False, f"步骤 {i} 的 dependent_on 必须是 null 或字符串"
            
            if "required_abilities" in step:
                if not isinstance(step["required_abilities"], list) or len(step["required_abilities"]) == 0:
                    return False, f"步骤 {i} 的 required_abilities 必须是非空数组"
                for tag in step["required_abilities"]:
                    if not isinstance(tag, str) or not tag.strip():
                        return False, f"步骤 {i} 的 required_abilities 包含无效标签"
            elif "required_ability" in step:
                if not isinstance(step["required_ability"], str) or not step["required_ability"].strip():
                    return False, f"步骤 {i} 的 required_ability 必须是非空字符串"
            
            if step["status"] != "pending":
                return False, f"步骤 {i} 的 status 必须是 'pending'"
        
        return True, ""
    
    def _validate_dependencies(self, task_tree: Dict) -> Tuple[bool, str]:
        """
        第二层：依赖关系校验（仅对 new_task 类型）
        
        Args:
            task_tree: 任务树字典
        
        Returns:
            (是否通过, 错误信息)
        """
        step_ids = {step["step_id"] for step in task_tree["task_tree"]}
        
        for step in task_tree["task_tree"]:
            dep = step.get("dependent_on")
            if dep is not None and dep not in step_ids:
                return False, f"步骤 {step['step_id']} 依赖不存在的步骤 '{dep}'"
        
        if self._has_circular_dependency(task_tree["task_tree"]):
            return False, "存在循环依赖，请修正依赖关系"
        
        return True, ""
    
    def _has_circular_dependency(self, steps: List[Dict]) -> bool:
        """
        检测循环依赖
        
        Args:
            steps: 步骤列表
        
        Returns:
            是否存在循环依赖
        """
        graph = {step["step_id"]: step.get("dependent_on") for step in steps}
        
        visited = set()
        rec_stack = set()
        
        def has_cycle(node):
            if node is None:
                return False
            visited.add(node)
            rec_stack.add(node)
            
            neighbor = graph.get(node)
            if neighbor in rec_stack:
                return True
            if neighbor not in visited:
                if has_cycle(neighbor):
                    return True
            
            rec_stack.remove(node)
            return False
        
        for step_id in graph:
            if step_id not in visited:
                if has_cycle(step_id):
                    return True
        
        return False
    
    def _create_default_task_tree(self) -> Dict:
        """
        创建默认任务树（用于解析失败时）
        
        Returns:
            默认任务树字典
        """
        return {
            "task_type": "new_task",
            "task_goal": "与用户进行对话",
            "total_steps": 1,
            "task_tree": [{
                "step_id": "step_1",
                "step_desc": "回复用户的内容",
                "dependent_on": None,
                "required_abilities": ["llm_response"],
                "status": "pending"
            }]
        }
