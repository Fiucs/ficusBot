#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :conversation.py
# @Time      :2026/03/01
# @Author    :Ficus

"""
对话上下文管理器模块

该模块提供对话上下文管理功能，负责管理系统提示词和对话历史。
"""

import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from colorama import Fore, Style
from loguru import logger

from agent.config.configloader import GLOBAL_CONFIG


DEFAULT_PROMPT_FILE = "agents.md"


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
        self._base_system_prompt: str = ""
        self.system_prompt: str = ""
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
                        self._init_system_prompt()
                        logger.info(f"[会话创建] ID: {self._session_id}, 持久化: True, 类型: 新建")
                else:
                    self._session_id = self._storage.create_session()
                    self._storage.set_current_session(self._session_id)
                    self._init_system_prompt()
                    logger.info(f"[会话创建] ID: {self._session_id}, 持久化: True, 类型: 新建（指定ID不存在）")
        else:
            self._init_system_prompt()
        
        logger.debug(f"[系统提示词] 长度: {len(self.system_prompt)} 字符")

    def _init_system_prompt(self):
        """
        初始化系统提示词（仅在需要时调用一次）。
        """
        if not self._base_system_prompt:
            self._base_system_prompt = self._build_system_prompt()
            self.system_prompt = self._base_system_prompt

    def reload_prompt(self) -> bool:
        """
        重新加载系统提示词（热加载）。
        
        从 prompts.md 文件重新读取提示词，无需重启程序。
        保留已注入的技能文档。
        
        Returns:
            bool: 重载是否成功
        """
        with self._lock:
            try:
                old_base = self._base_system_prompt
                self._base_system_prompt = self._build_system_prompt()
                
                if self._injected_skills:
                    injected_content = self._extract_injected_content()
                    self.system_prompt = self._base_system_prompt
                    if injected_content:
                        placeholder = "{INJECTED_SKILLS}"
                        if placeholder in self.system_prompt:
                            self.system_prompt = self.system_prompt.replace(placeholder, injected_content)
                        else:
                            self.system_prompt = self.system_prompt + "\n" + injected_content
                else:
                    self.system_prompt = self._base_system_prompt
                
                logger.info(f"[系统提示词] 热加载完成，长度: {len(self.system_prompt)} 字符")
                return True
            except Exception as e:
                logger.error(f"[系统提示词] 热加载失败: {e}")
                return False

    def _extract_injected_content(self) -> str:
        """
        从当前 system_prompt 中提取已注入的技能文档内容。
        
        Returns:
            str: 提取的注入内容，无注入时返回空字符串
        """
        import re
        pattern = rf"{re.escape(self.DOC_BEGIN_MARKER)}.*?{re.escape(self.DOC_END_MARKER)}[^\n]*"
        matches = re.findall(pattern, self.system_prompt, flags=re.DOTALL)
        return "\n\n".join(matches) if matches else ""

    def _build_system_prompt(self) -> str:
        """
        构建基础系统提示词（不含技能文档注入）。
        
        从 workspace/prompts.md 文件读取提示词模板，支持动态配置。
        如果文件不存在或读取失败，使用内置的默认提示词。
        
        Returns:
            str: 基础系统提示词
        """
        if self.custom_system_prompt:
            return self.custom_system_prompt
        
        workspace_root = GLOBAL_CONFIG.get("workspace_root", "未配置")
        allow_list = GLOBAL_CONFIG.get("file_allow_list", [])
        allow_list_str = "\n".join([f"  - {p}" for p in allow_list])
        
        prompt_content = self._load_prompt_from_file()
        
        if prompt_content:
            prompt_content = prompt_content.replace("{workspace_root}", workspace_root)
            return prompt_content
        # 不存在则报错，直接结束程序
        logger.error(f"[系统提示词] 未找到 prompts.md 文件，工作区根目录: {workspace_root}")
        raise FileNotFoundError(f"prompts.md 文件不存在于 {workspace_root}")
        # return self._get_default_prompt(workspace_root)

    def _load_prompt_from_file(self) -> Optional[str]:
        """
        从文件加载提示词模板。
        
        尝试从以下位置加载 prompts.md：
        1. workspace_root/prompts.md
        2. workspace/prompts.md（相对于项目根目录）
        
        Returns:
            Optional[str]: 提示词内容，加载失败返回 None
        """
        workspace_root = GLOBAL_CONFIG.get("workspace_root", "")
        
        search_paths = []
        
        if workspace_root:
            search_paths.append(Path(workspace_root) / DEFAULT_PROMPT_FILE)
        
        project_root = Path(__file__).parent.parent.parent
        search_paths.append(project_root / "workspace" / DEFAULT_PROMPT_FILE)
        
        for prompt_path in search_paths:
            if prompt_path.exists() and prompt_path.is_file():
                try:
                    with open(prompt_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        logger.info(f"[系统提示词] 从文件加载成功: {prompt_path}")
                        return content
                except Exception as e:
                    logger.warning(f"[系统提示词] 读取文件失败 {prompt_path}: {e}")
        
        logger.warning("[系统提示词] 未找到 prompts.md 文件，使用内置默认提示词")
        return None

   

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
                    self._init_system_prompt()
                    
                    # 如果有注入的技能，需要重建 system_prompt
                    if self._injected_skills:
                        # system_prompt 保持从存储加载的值（包含已注入的技能文档）
                        self.system_prompt = data.get("system_prompt", self._base_system_prompt)
                    
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
