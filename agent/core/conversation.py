#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :conversation.py
# @Time      :2026/03/01
# @Author    :Ficus

"""
对话上下文管理器模块

该模块提供对话上下文管理功能，负责管理系统提示词和对话历史。
"""

import re
import threading
from typing import Any, Dict, List, Optional, Set

from colorama import Fore, Style
from loguru import logger

from agent.config.configloader import GLOBAL_CONFIG


class ConversationManager:
    """
    对话上下文管理器，负责管理系统提示词和对话历史。

    功能说明:
        - 构建和维护系统提示词（system prompt）
        - 管理对话历史记录（user/assistant/tool消息）
        - 支持技能文档的动态注入和清理
        - 控制对话历史长度，防止上下文过长
        - 支持会话持久化存储

    核心方法:
        - add_message: 添加对话消息
        - add_tool_result: 添加工具执行结果
        - get_messages: 获取完整对话消息（含system prompt）
        - inject_skill_document: 动态注入技能文档到system prompt
        - clear_injected_document: 清理注入的技能文档
        - clear: 清空对话历史
        - save: 保存会话到存储
        - load: 从存储加载会话

    技能文档注入机制:
        - 使用标记包裹注入的文档，便于后续清理
        - 注入格式: ### BEGIN_INJECTED_DOC ###\n{doc}\n### END_INJECTED_DOC ###
        - 注入后大模型能看到完整的技能说明，指导后续工具调用

    会话持久化:
        - 支持会话保存到 TinyDB 存储
        - 支持从存储加载历史会话
        - 支持自动保存

    线程安全:
        - 使用 RLock（可重入锁）保护所有数据变更操作
        - 支持同一线程多次获取锁（如 clear() 内部调用 clear_injected_document()）

    Attributes:
        DOC_BEGIN_MARKER: 技能文档开始标记
        DOC_END_MARKER: 技能文档结束标记
        history: 对话历史记录列表
        max_rounds: 最大历史轮数
        system_prompt: 当前系统提示词
        _lock: 线程锁
        _base_system_prompt: 基础系统提示词（不含注入内容）
        _injected_skills: 已注入的技能名称集合
        _enable_persistence: 是否启用持久化
        _storage: 会话存储实例
        _session_id: 当前会话ID
    """

    DOC_BEGIN_MARKER = "### BEGIN_INJECTED_DOC ###"
    DOC_END_MARKER = "### END_INJECTED_DOC ###"

    def __init__(self, session_id: Optional[str] = None, enable_persistence: bool = True):
        """
        初始化对话管理器。

        Args:
            session_id: 会话ID，为None时尝试恢复上次会话或创建新会话
            enable_persistence: 是否启用会话持久化，默认True
        """
        self._lock = threading.RLock()
        self.history: List[Dict[str, str]] = []
        self.max_rounds = GLOBAL_CONFIG.get("conversation.max_history_rounds", 10)
        self.custom_system_prompt: Optional[str] = None
        self._base_system_prompt = self._build_system_prompt()
        self.system_prompt = self._base_system_prompt
        self._injected_skills: Set[str] = set()
        
        self._enable_persistence = enable_persistence and GLOBAL_CONFIG.get("session.enable_persistence", True)
        self._storage: Optional['SessionStorage'] = None
        self._session_id: Optional[str] = None
        
        if self._enable_persistence:
            from agent.storage import SessionStorage
            storage_dir = GLOBAL_CONFIG.get("session.storage_dir", "./sessions")
            max_sessions = GLOBAL_CONFIG.get("session.max_sessions", 100)
            expire_days = GLOBAL_CONFIG.get("session.expire_days", 30)
            
            self._storage = SessionStorage(
                storage_path=f"{storage_dir}/sessions.json",
                max_sessions=max_sessions,
                expire_days=expire_days
            )
            
            if session_id and self._storage.exists(session_id):
                self._session_id = session_id
                self._load_from_storage()
                self._storage.set_current_session(self._session_id)
                logger.info(f"[会话加载] ID: {self._session_id}, 持久化: True, 类型: 恢复指定会话")
            else:
                if not session_id:
                    current_session = self._storage.get_current_session()
                    if current_session and self._storage.exists(current_session):
                        self._session_id = current_session
                        self._load_from_storage()
                        logger.info(f"[会话加载] ID: {self._session_id}, 持久化: True, 类型: 恢复上次会话")
                    else:
                        self._session_id = self._storage.create_session()
                        self._storage.set_current_session(self._session_id)
                        logger.info(f"[会话创建] ID: {self._session_id}, 持久化: True, 类型: 新建")
                else:
                    self._session_id = self._storage.create_session()
                    self._storage.set_current_session(self._session_id)
                    logger.info(f"[会话创建] ID: {self._session_id}, 持久化: True, 类型: 新建（指定ID不存在）")
        
        logger.debug(f"[系统提示词] 长度: {len(self.system_prompt)} 字符")

    def _build_system_prompt(self) -> str:
        """
        构建基础系统提示词（不含技能文档注入）。
        
        Returns:
            str: 基础系统提示词
        """
        if self.custom_system_prompt:
            return self.custom_system_prompt
        
        workspace_root = GLOBAL_CONFIG.get("workspace_root", "未配置")
        allow_list = GLOBAL_CONFIG.get("file_allow_list", [])
        allow_list_str = "\n".join([f"  - {p}" for p in allow_list])
        return f"""你是一个严谨自主的智能助手，严格遵循ReAct(Reasoning-Action)框架。

# 核心原则
0. **简洁优先**：回答简短直接，思考不超过35字，不啰嗦不重复。
1. 自主优先：尽量独立完成任务，仅在需要用户澄清时才询问。
2. 最小干预：使用最少的工具和步骤完成任务。
3. 错误处理，在执行任务期间遇到的问题最终要报告给用户。
3. 工作区根目录：{workspace_root}


# ReAct工作流程
每轮对话遵循：思考 → 行动 → 观察 → 回答 的迭代循环。始终在思考阶段评估所有可用信息，包括注入的技能和历史调用状态。

## 思考(Reasoning)
分析用户意图，判断是否需要工具或技能：
- 如果已有足够信息，直接回答。
- 如果需要外部信息或操作，检查可用工具和技能。
- 如果涉及技能：
  - 先检查是否已注入：查看系统提示中的"技能文档"部分。如果对应文档已存在，表示技能已可用。
  - 如果未注入：仅首次考虑调用 skill.xxx 注入文档（整个对话建议只调用1次）。
  - 如果已注入：不要再次调用 skill.xxx，直接阅读注入文档，分解步骤为ReAct轮次，使用文档指定的工具（如 shell.exec）。
- 分解任务为小步，确保不重复历史行动。

## 行动(Action)
如需调用工具，通过Function Calling机制：
1. 选择正确的工具名（如 file.read、shell.exec、browser.navigate 等）。
2. **工具名称必须是一个有效的工具名字符串，绝不能为 None、空字符串或任何无效值**。
3. **必须提供所有必填参数的具体值。严禁输出 "arguments": {{}} 或完全省略 arguments，否则会导致 name=None 的错误**。
如果涉及技能，按文档步骤逐步行动（例如，先检查前提工具，再执行核心工具）。避免重复调用 skill.xxx。

## 观察(Observation)
工具执行后，根据结果进行下一步：
- 结果满足需求 → 生成最终回答。
- 需要更多信息 → 返回思考，继续迭代。
- 如果失败或检测到重复：在思考中评估备选路径（如文档中的fallback），仅无解时简短报告用户。如果系统提示重复调用错误，请停止 skill.xxx 并切换文档工具。

# 当前可用技能
## 技能列表
{{INJECTED_SKILLS_LIST}}

## 技能文档
{{INJECTED_SKILLS}}

# 技能使用规则
技能作为ReAct的扩展，按需集成：
1. 在思考阶段检查用户是否要求特定技能，或任务是否匹配可用技能列表。
2. 如果匹配且未注入：仅首次调用 skill.xxx 注入文档。
3. 已注入后：在思考中仔细阅读对应技能的注入文档（标记为 ### BEGIN_INJECTED_DOC ### 的部分），分解执行步骤为多个ReAct轮次。
4. 逐步按照文档执行：每轮仅处理一小步（如先验证环境，再调用工具），观察结果后继续。整个对话建议只调用1次 skill.xxx。
5. 如果技能工具失败或重复：在下一思考中尝试文档中的备选步骤，或切换普通工具。不要重新调用技能工具，直接向用户说明原因。
6. 必须通过正确的工具调用实际执行，工具名称必须明确。

## 技能使用示例
思考：用户要求网络搜索，exa-web-search-free 可用但未注入完整文档。
行动：调用 skill.exa-web-search-free 注入文档（仅首次）。

思考：exa-web-search-free 已注入（文档存在），检查历史无重复；步骤包括验证API然后搜索。
行动：调用 shell.exec 验证API（第一步）。

思考：验证成功，观察结果OK；下一步是搜索。确认无 skill.xxx 重复。
行动：调用 shell.exec 执行搜索（第二步）。

思考：shell.exec 失败，或观察到重复调用错误。
行动：评估备选（如手动搜索），报告用户"技能执行失败：API无效"，不要重试 skill.xxx。

# 工具说明
可用工具通过API的tools参数传递，如 file.read、shell.exec、browser.navigate 等。工具名称必须明确。

## 子代理委托
agent.xxx.delegate 工具可将任务委托给专业子代理。查看工具描述选择合适的子代理，提供 task 参数即可。

# 响应规则
- **只有真正需要调用工具时才输出 function call，否则直接输出最终答案，绝不要输出 name=None 或 arguments={{}} 的无效调用**。
- 调用工具时：简要说明思考过程，然后正确调用工具。
- 直接回答时：输出最终答案。
- 一次最多调用3个工具。
- **严禁输出工具名称为 None 或 arguments 为空的调用，这是严重错误，会导致"工具名称为空"失败**。

#浏览器操做
## 浏览器操作技巧
- 对于已知的搜索URL格式，可直接构造URL：
  - 百度：https://www.baidu.com/s?wd=关键词
  - Google：https://www.google.com/search?q=关键词
  - Bing：https://www.bing.com/search?q=关键词
- 重要：构造URL后必须调用 browser.get_state() 验证页面内容
- 如果验证失败或URL格式未知，改用逐步操作：navigate → get_state → input → click
"""

    def add_message(self, role: str, content: str, tool_calls: List[Dict] = None):
        """
        添加对话消息到历史记录（线程安全）。
        
        Args:
            role: 消息角色（user/assistant/system/tool）
            content: 消息内容
            tool_calls: 工具调用列表（可选）
        """
        with self._lock:
            message = {"role": role, "content": content}
            if tool_calls:
                message["tool_calls"] = tool_calls
            self.history.append(message)
            if len(self.history) > self.max_rounds * 2:
                self.history = self.history[-self.max_rounds * 2:]

    def add_tool_result(self, tool_call_id: str, tool_name: str, content: str):
        """
        添加工具执行结果到对话历史（线程安全）。
        
        Args:
            tool_call_id: 工具调用ID
            tool_name: 工具名称
            content: 执行结果内容
        """
        with self._lock:
            self.history.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": tool_name,
                "content": content
            })

    def get_messages(self) -> List[Dict[str, str]]:
        """
        获取完整对话消息列表（包含system prompt，线程安全）。
        
        Returns:
            List[Dict]: 完整消息列表
        """
        with self._lock:
            return [{"role": "system", "content": self.system_prompt}] + self.history.copy()

    def inject_skill_document(self, skill_name: str, skill_doc: str) -> bool:
        """
        将技能文档注入到system prompt的指定位置（{{INJECTED_SKILLS}}占位符处）。

        注入逻辑:
            1. 检查该技能是否已注入，如果已注入则跳过（避免重复）
            2. 将技能文档包裹在带技能名称的标记中
            3. 替换 {{INJECTED_SKILLS}} 占位符，保留其他已注入的技能文档
            4. 更新system_prompt和注入技能列表

        Args:
            skill_name: 技能名称
            skill_doc: 技能文档内容（Markdown格式）

        Returns:
            bool: 注入是否成功
        """
        with self._lock:
            try:
                if skill_name in self._injected_skills:
                    logger.info(f"{Fore.CYAN}技能 '{skill_name}' 文档已存在，跳过重复注入{Style.RESET_ALL}")
                    return True

                new_skill_content = f"""{self.DOC_BEGIN_MARKER} [{skill_name}]

# 技能: {skill_name}

{skill_doc}

{self.DOC_END_MARKER} [{skill_name}]"""

                placeholder = "{INJECTED_SKILLS}"
                if placeholder in self.system_prompt:
                    self.system_prompt = self.system_prompt.replace(placeholder, new_skill_content)
                else:
                    last_end_marker = self.system_prompt.rfind(f"{self.DOC_END_MARKER} [")
                    if last_end_marker != -1:
                        insert_pos = self.system_prompt.find("\n", last_end_marker) + 1
                        self.system_prompt = self.system_prompt[:insert_pos] + "\n" + new_skill_content + "\n" + self.system_prompt[insert_pos:]
                    else:
                        logger.warning(f"{Fore.YELLOW}未找到技能注入标记，追加到system prompt末尾{Style.RESET_ALL}")
                        self.system_prompt = self.system_prompt + "\n" + new_skill_content

                self._injected_skills.add(skill_name)

                logger.info(f"{Fore.CYAN}技能文档已注入: {skill_name}, 当前注入技能数: {len(self._injected_skills)}, system prompt长度: {len(self.system_prompt)}{Style.RESET_ALL}")
                return True
            except Exception as e:
                logger.error(f"{Fore.RED}技能文档注入失败: {str(e)}{Style.RESET_ALL}")
            return False

    def clear_injected_document(self, skill_name: Optional[str] = None) -> bool:
        """
        清理注入的技能文档（线程安全）。

        清理逻辑:
            - 如果指定skill_name，只清理该技能的文档
            - 如果未指定skill_name，清理所有注入的技能文档，恢复基础system prompt（包含{{INJECTED_SKILLS}}占位符）

        Args:
            skill_name: 要清理的技能名称，为None时清理所有

        Returns:
            bool: 清理是否成功
        """
        with self._lock:
            try:
                if skill_name:
                    if skill_name in self._injected_skills:
                        pattern = rf"{re.escape(self.DOC_BEGIN_MARKER)} \[{re.escape(skill_name)}\].*?{re.escape(self.DOC_END_MARKER)} \[{re.escape(skill_name)}\]\n?"
                        self.system_prompt = re.sub(pattern, "", self.system_prompt, flags=re.DOTALL)
                        self._injected_skills.discard(skill_name)
                        
                        if not self._injected_skills:
                            self.system_prompt = self._base_system_prompt
                        
                        logger.info(f"{Fore.CYAN}清理指定技能文档: {skill_name}, 剩余注入技能: {self._injected_skills}{Style.RESET_ALL}")
                    return True
                else:
                    if self._injected_skills:
                        logger.info(f"{Fore.CYAN}清理所有注入的技能文档: {self._injected_skills}{Style.RESET_ALL}")
                        self._injected_skills.clear()

                    self.system_prompt = self._base_system_prompt
                    return True
            except Exception as e:
                logger.error(f"{Fore.RED}清理技能文档失败: {str(e)}{Style.RESET_ALL}")
                return False

    def has_injected_skill(self, skill_name: Optional[str] = None) -> bool:
        """
        检查是否有注入的技能文档（线程安全）。

        Args:
            skill_name: 技能名称，为None时检查是否有任何注入的技能

        Returns:
            bool: 是否有注入的技能文档
        """
        with self._lock:
            if skill_name:
                return skill_name in self._injected_skills
            return len(self._injected_skills) > 0

    def get_injected_skills(self) -> Set[str]:
        """
        获取所有已注入的技能名称集合（线程安全）。
        
        Returns:
            Set[str]: 已注入的技能名称集合副本
        """
        with self._lock:
            return self._injected_skills.copy()

    def inject_skill_list(self, skill_list_str: str) -> bool:
        """
        将技能列表注入到 system prompt 的指定位置（{{INJECTED_SKILLS_LIST}} 占位符处）。
        
        注入逻辑:
            1. 替换 {{INJECTED_SKILLS_LIST}} 占位符
            2. 更新 _base_system_prompt 和 system_prompt
        
        Args:
            skill_list_str: 格式化的技能列表字符串（OpenClaw 风格）
            
        Returns:
            bool: 注入是否成功
        """
        with self._lock:
            try:
                placeholder = "{INJECTED_SKILLS_LIST}"
                if placeholder in self._base_system_prompt:
                    self._base_system_prompt = self._base_system_prompt.replace(placeholder, skill_list_str)
                    self.system_prompt = self._base_system_prompt
                    logger.info(f"[技能列表注入] 成功注入 {skill_list_str.count('- **')} 个技能到 system prompt")
                    return True
                else:
                    logger.warning("[技能列表注入] 未找到 {INJECTED_SKILLS_LIST} 占位符")
                    return False
            except Exception as e:
                logger.error(f"[技能列表注入] 失败: {str(e)}")
                return False

    def clear(self):
        """
        清空对话历史并恢复基础system prompt（线程安全）。
        
        Returns:
            Dict: 操作结果
        """
        with self._lock:
            self.history = []
            self._injected_skills.clear()
            self.system_prompt = self._base_system_prompt
        return {"status": "success", "message": "对话上下文已清空"}

    @property
    def session_id(self) -> Optional[str]:
        """
        获取当前会话ID。
        
        Returns:
            Optional[str]: 当前会话ID
        """
        return self._session_id

    def save(self) -> bool:
        """
        保存会话到存储（线程安全）。

        Returns:
            bool: 保存是否成功
        """
        if not self._enable_persistence or not self._storage:
            logger.debug("[会话保存] 持久化未启用，跳过保存")
            return False
        
        with self._lock:
            try:
                history_count = len(self.history)
                success = self._storage.save_session(self._session_id, {
                    "history": self.history,
                    "system_prompt": self.system_prompt,
                    "base_system_prompt": self._base_system_prompt,
                    "injected_skills": list(self._injected_skills)
                })
                if success:
                    logger.info(f"[会话保存] ID: {self._session_id}, 消息数: {history_count}, 结果: 成功")
                else:
                    logger.warning(f"[会话保存] ID: {self._session_id}, 消息数: {history_count}, 结果: 失败")
                return success
            except Exception as e:
                logger.error(f"[会话保存] ID: {self._session_id}, 错误: {e}")
                return False

    def _load_from_storage(self) -> bool:
        """
        从存储加载会话数据（内部方法，线程安全）。

        Returns:
            bool: 加载是否成功
        """
        if not self._storage:
            return False
        
        with self._lock:
            try:
                data = self._storage.load_session(self._session_id)
                if data:
                    self.history = data.get("history", [])
                    self._injected_skills = set(data.get("injected_skills", []))
                    
                    # _base_system_prompt 始终使用最新代码生成的，不从存储加载
                    # 这样可以确保代码更新后，旧的会话也能使用新的 system prompt 结构
                    self._base_system_prompt = self._build_system_prompt()
                    
                    # 如果有注入的技能，需要重建 system_prompt
                    if self._injected_skills:
                        # system_prompt 保持从存储加载的值（包含已注入的技能文档）
                        self.system_prompt = data.get("system_prompt", self._base_system_prompt)
                    else:
                        self.system_prompt = self._base_system_prompt
                    
                    logger.info(f"[会话加载] ID: {self._session_id}, 消息数: {len(self.history)}, 结果: 成功")
                    return True
                logger.warning(f"[会话加载] ID: {self._session_id}, 结果: 会话不存在")
                return False
            except Exception as e:
                logger.error(f"[会话加载] ID: {self._session_id}, 错误: {e}")
                return False

    def delete_session(self) -> bool:
        """
        删除当前会话（线程安全）。

        Returns:
            bool: 删除是否成功
        """
        if not self._enable_persistence or not self._storage:
            return False
        
        with self._lock:
            try:
                success = self._storage.delete_session(self._session_id)
                if success:
                    logger.info(f"会话删除成功: {self._session_id}")
                    self._session_id = None
                    self.history = []
                    self._injected_skills.clear()
                    self.system_prompt = self._base_system_prompt
                return success
            except Exception as e:
                logger.error(f"会话删除失败: {e}")
                return False

    def switch_session(self, session_id: str) -> bool:
        """
        切换到指定会话（线程安全）。

        Args:
            session_id: 目标会话ID

        Returns:
            bool: 切换是否成功
        """
        if not self._enable_persistence or not self._storage:
            logger.warning("[会话切换] 持久化未启用，无法切换会话")
            return False
        
        if not self._storage.exists(session_id):
            logger.warning(f"[会话切换] 会话不存在: {session_id}")
            return False
        
        with self._lock:
            try:
                if self._session_id:
                    self.save()
                
                self._session_id = session_id
                self._load_from_storage()
                self._storage.set_current_session(session_id)
                
                logger.info(f"[会话切换] 成功切换到会话: {session_id}")
                return True
            except Exception as e:
                logger.error(f"[会话切换] 切换失败: {e}")
                return False

    def list_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        列出所有会话（线程安全）。

        Args:
            limit: 返回数量限制

        Returns:
            List[Dict]: 会话列表，每项包含 session_id, first_message, metadata
        """
        if not self._enable_persistence or not self._storage:
            return []
        
        with self._lock:
            sessions = self._storage.list_sessions(limit=limit)
            result = []
            for s in sessions:
                session_id = s.get("session_id")
                first_msg = self._storage.get_first_message(session_id)
                result.append({
                    "session_id": session_id,
                    "first_message": first_msg or "(空会话)",
                    "metadata": s.get("metadata", {}),
                    "is_current": session_id == self._session_id
                })
            return result

    def create_new_session(self) -> str:
        """
        创建新会话并切换到该会话（线程安全）。

        Returns:
            str: 新会话ID，失败返回空字符串
        """
        if not self._enable_persistence or not self._storage:
            return ""
        
        with self._lock:
            try:
                if self._session_id:
                    self.save()
                
                new_session_id = self._storage.create_session()
                self._session_id = new_session_id
                self.history = []
                self._injected_skills.clear()
                self.system_prompt = self._base_system_prompt
                self._storage.set_current_session(new_session_id)
                
                logger.info(f"[会话创建] 新会话已创建并激活: {new_session_id}")
                return new_session_id
            except Exception as e:
                logger.error(f"[会话创建] 创建失败: {e}")
                return ""

    def cleanup_tool_messages(self) -> Dict[str, Any]:
        """
        清理对话历史中的工具调用临时信息（线程安全）。

        清理内容:
            - 移除所有 role='tool' 的消息
            - 移除 assistant 消息中的 tool_calls 字段
            - 合并连续的 assistant 消息（保留最后一个有内容的）
            - 保留 user 和 assistant 的纯文本内容

        日志记录:
            - 被清理的 tool 消息数量
            - 被清理的 tool_calls 信息
            - 合并的 assistant 消息信息

        Returns:
            Dict[str, Any]: 清理统计信息
                - removed_tool_messages: 移除的 tool 消息数量
                - cleaned_assistant_messages: 清理的 assistant 消息数量
                - merged_assistant_messages: 合并的 assistant 消息数量
        """
        with self._lock:
            original_count = len(self.history)
            removed_tool_count = 0
            cleaned_assistant_count = 0
            merged_assistant_count = 0
            cleaned_tool_details = []
            cleaned_assistant_details = []

            logger.info(f"{Fore.CYAN}[工具消息清理] 开始清理，原始消息数: {original_count}{Style.RESET_ALL}")

            # 第一步：移除 tool 消息，清理 assistant 消息中的 tool_calls
            temp_history = []
            for idx, msg in enumerate(self.history):
                role = msg.get("role", "")

                if role == "tool":
                    removed_tool_count += 1
                    tool_name = msg.get("name", "unknown")
                    tool_call_id = msg.get("tool_call_id", "unknown")
                    content_preview = (msg.get("content", ""))[:100]
                    cleaned_tool_details.append({
                        "index": idx,
                        "tool_name": tool_name,
                        "tool_call_id": tool_call_id,
                        "content_preview": content_preview
                    })
                    logger.info(f"{Fore.CYAN}  移除 tool 消息 [{idx}]: {tool_name} (id: {tool_call_id}){Style.RESET_ALL}")
                    continue

                if role == "assistant" and "tool_calls" in msg:
                    tool_calls = msg.get("tool_calls", [])
                    if tool_calls:
                        cleaned_assistant_count += 1
                        tool_names = [tc.get("function", {}).get("name", "unknown") for tc in tool_calls]
                        cleaned_assistant_details.append({
                            "index": idx,
                            "tool_names": tool_names
                        })
                        logger.info(f"{Fore.CYAN}  清理 assistant 消息 [{idx}] 的 tool_calls: {tool_names}{Style.RESET_ALL}")
                        msg = {k: v for k, v in msg.items() if k != "tool_calls"}

                temp_history.append(msg)

            # 第二步：合并连续的 assistant 消息
            # 策略：如果连续的 assistant 消息中，前面的内容为空或只有 tool_calls（已被清理），
            # 则只保留最后一个有内容的 assistant 消息
            new_history = []
            pending_assistant = None

            for idx, msg in enumerate(temp_history):
                role = msg.get("role", "")
                content = msg.get("content", "")

                if role == "assistant":
                    if pending_assistant is not None:
                        # 之前有未处理的 assistant，说明是连续的
                        merged_assistant_count += 1
                        logger.info(f"{Fore.CYAN}  合并连续的 assistant 消息，保留后一个 [{idx}]{Style.RESET_ALL}")
                    # 暂存当前 assistant，继续看下一个
                    pending_assistant = msg
                else:
                    # 遇到非 assistant 消息，先处理暂存的 assistant
                    if pending_assistant is not None:
                        new_history.append(pending_assistant)
                        pending_assistant = None
                    new_history.append(msg)

            # 处理最后可能暂存的 assistant
            if pending_assistant is not None:
                new_history.append(pending_assistant)

            self.history = new_history
            final_count = len(self.history)

            logger.info(f"[工具消息清理] 完成: 移除 {removed_tool_count} 条 tool 消息，清理 {cleaned_assistant_count} 条 assistant 消息的 tool_calls，合并 {merged_assistant_count} 条 assistant 消息，消息数: {original_count} -> {final_count}")

            return {
                "original_count": original_count,
                "final_count": final_count,
                "removed_tool_messages": removed_tool_count,
                "cleaned_assistant_messages": cleaned_assistant_count,
                "merged_assistant_messages": merged_assistant_count,
                "cleaned_tools": cleaned_tool_details,
                "cleaned_assistants": cleaned_assistant_details
            }
