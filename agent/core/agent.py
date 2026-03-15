#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :agent.py
# @Time      :2026/03/07
# @Author    :Ficus

"""
核心 Agent 调度器模块

该模块定义了核心 Agent 类，负责协调对话、工具调用和技能执行。
"""
import json
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, TYPE_CHECKING, Union

from colorama import Fore, Style
from loguru import logger

from agent.config.configloader import GLOBAL_CONFIG
from agent.core.conversation import ConversationManager
from agent.core.agent_initializer import AgentInitializer
from agent.core.token_counter import TokenCounter
from agent.fileSystem.filesystem import FileSystemTool
from agent.provider.llmclient import LLMClient
from agent.skill.skill_loader import SkillLoader
from agent.memory import MemorySystem
from agent.tool.shelltool import ShellTool
from agent.tool.tooladapter import ToolAdapter

# 导入反思机制模块
from agent.core.reflection import (
    ReflectionConfig,
    ReflectionEngine,
    StagePipeline,
    StageContext,
    DecomposeStage,
    ExecutionStage,
    SummarizeStage,
)

# 导入拆分的工具函数和类
from agent.core.agent_utils import (
    _format_content_for_print,
    _extract_reasoning_content,
    _extract_and_remove_think_tags,
    print_conversation_history,
    ToolManager,
)
from agent.core.agent_task_executor import TaskExecutor

if TYPE_CHECKING:
    from agent.config.agent_config import AgentConfig


class Agent:
    """
    核心Agent调度器，负责协调对话、工具调用和技能执行。
    
    功能说明:
        - 管理对话上下文和历史记录
        - 处理用户输入并调用大模型
        - 支持工具调用（文件操作、Shell命令、技能等）
        - 支持流式和非流式响应
        - 支持技能自动检测和调用
        - 支持多Agent架构和子代理委托
        - 支持任务拆解和断点续跑
    
    核心方法:
        - chat: 非流式对话（用于CLI和API）
        - chat_stream: 流式对话（用于旧API兼容）
        - reload: 重载所有组件配置
    
    配置项:
        - max_tool_calls: 最大工具调用次数，默认10次
        - agent_config: Agent配置对象，支持多Agent架构
        - delegation_depth: 当前委托深度，用于子代理调用
    """
    
    mcp_manager: Any
    mcp_tool_adapter: Any
    browser_tool: Any
    memory_system: Any
    task_decomposer: Any
    task_tree_manager: Any
    heartbeat_manager: Any
    tool_manager: Any
    task_executor: Any
    
    # 反思机制相关属性
    _reflection_config: ReflectionConfig
    _reflection_engine: Optional[ReflectionEngine]
    _stage_pipeline: Optional[StagePipeline]
    
    def __init__(
        self, 
        session_id: Optional[str] = None, 
        enable_persistence: bool = True,
        agent_config: Optional["AgentConfig"] = None,
        delegation_depth: int = 0
    ):
        """
        初始化 Agent。

        参数:
            session_id: 会话ID，为None时自动创建新会话
            enable_persistence: 是否启用会话持久化，默认True
            agent_config: Agent配置对象，为None时使用默认配置
            delegation_depth: 当前委托深度，用于子代理调用时防止无限递归
        """
        self.agent_config = agent_config
        self.delegation_depth = delegation_depth
        self.agent_id = agent_config.agent_id if agent_config else "default"
        
        # 确保 Agent 专属工作目录存在
        if agent_config:
            agent_config.ensure_workspace_dirs()
        
        self.file_tool = FileSystemTool(agent_config)
        self.shell_tool = ShellTool(agent_config)
        self.skill_loader = SkillLoader()
        self.tool_adapter = ToolAdapter(
            self.file_tool, 
            self.shell_tool, 
            self.skill_loader,
            delegation_depth=delegation_depth
        )
        self.conversation = ConversationManager(session_id, enable_persistence)
        
        if agent_config and agent_config.system_prompt:
            self.conversation.custom_system_prompt = agent_config.system_prompt
        
        if agent_config and agent_config.model:
            self.llm_client = LLMClient(default_model=agent_config.model)
            llm_params = agent_config.get_llm_params()
            self.llm_client.apply_preset(llm_params)
        else:
            self.llm_client = LLMClient()
        
        if agent_config and agent_config.max_tool_calls:
            self.max_tool_calls = agent_config.max_tool_calls
        else:
            self.max_tool_calls = GLOBAL_CONFIG.get("llm", {}).get("max_tool_calls", 10)
        
        self._last_skill_call: Optional[str] = None
        self._last_skill_repeat_count: int = 0
        self._max_skill_repeats = 1
        self._blocked_skills: set = set()
        self._auto_save = GLOBAL_CONFIG.get("session.auto_save", True)
        
        # 初始化反思机制（默认启用）
        self._reflection_config = ReflectionConfig()
        self._reflection_engine = None
        self._stage_pipeline = None
        
        # 初始化工具管理器和任务执行器
        self.tool_manager = ToolManager(self)
        self.task_executor = TaskExecutor(self)
        
        logger.info(f"{Fore.CYAN}初始化 Agent: {self.agent_id}, 最大工具调用次数: {self.max_tool_calls}{Style.RESET_ALL}")
        
        AgentInitializer.init_mcp(self)
        AgentInitializer.init_browser(self)
        AgentInitializer.init_memory(self)
        AgentInitializer._start_config_watcher(self)
        AgentInitializer._start_tool_index_watcher(self)
        AgentInitializer.init_task_decomposition(self)
        
        # 默认启用反思机制（新架构）------------------------------------------
        self.enable_reflection(
            enabled=True,
            max_rounds=2, # 最大反思轮数，默认2轮
            decompose={"before": False, "after": False},
            execute={"before": False, "after": False},
            summarize={"before": False, "after": False}
        )

    def reload_config_only(self):
        """
        轻量级配置热更新（不重新初始化工具和记忆系统）。
        
        功能说明:
            - 重载全局配置
            - 更新 Agent 配置
            - 重载 LLM 客户端配置
            - 热加载系统提示词
            
        注意:
            此方法用于配置文件热加载，只更新配置相关的部分。
            如需完整重载所有组件，请使用 reload() 方法。
        """
        GLOBAL_CONFIG.reload()
        
        current_model = self.llm_client.current_model_alias
        
        if self.agent_config:
            from agent.config.agent_config import AgentConfig
            agents_config = GLOBAL_CONFIG.get("agents", {})
            agent_config_dict = agents_config.get(self.agent_id, {})
            if agent_config_dict:
                new_config = AgentConfig.from_dict(self.agent_id, agent_config_dict)
                if new_config:
                    self.agent_config = new_config
                    if new_config.model:
                        current_model = new_config.model
        
        self.llm_client.reload_config()
        
        if self.agent_config:
            llm_params = self.agent_config.get_llm_params()
            self.llm_client.apply_preset(llm_params)
            logger.info(f"{Fore.CYAN}[Reload] LLM 参数已更新: temperature={llm_params.get('temperature')}, max_tokens={llm_params.get('max_tokens')}, timeout={llm_params.get('timeout')}{Style.RESET_ALL}")
        
        if current_model != self.llm_client.current_model_alias:
            switch_result = self.llm_client.switch_model(current_model)
            logger.info(f"{Fore.CYAN}[Reload] 模型已切换: {current_model}{Style.RESET_ALL}")
        
        self.conversation.reload_prompt()
        
        logger.info(f"{Fore.GREEN}✅ 配置已热更新{Style.RESET_ALL}")

    def reload(self):
        """
        重载所有组件配置。
        
        功能说明:
            - 重载全局配置
            - 重新加载 Agent 配置（如果使用 agent_config）
            - 重新初始化所有工具（文件、Shell、技能）
            - 重新初始化 MCP 模块
            - 重新初始化浏览器工具
            - 重新初始化记忆系统
            - 重载 LLM 客户端配置
            - 热加载系统提示词（从 prompts.md）
        """
        GLOBAL_CONFIG.reload()
        
        current_model = self.llm_client.current_model_alias
        
        if self.agent_config:
            from agent.config.agent_config import AgentConfig
            agents_config = GLOBAL_CONFIG.get("agents", {})
            agent_config_dict = agents_config.get(self.agent_id, {})
            if agent_config_dict:
                new_config = AgentConfig.from_dict(self.agent_id, agent_config_dict)
                if new_config:
                    self.agent_config = new_config
                    if new_config.model:
                        current_model = new_config.model
        
        self.llm_client.reload_config()
        
        if self.agent_config:
            llm_params = self.agent_config.get_llm_params()
            self.llm_client.apply_preset(llm_params)
            logger.info(f"{Fore.CYAN}[Reload] LLM 参数已更新: temperature={llm_params.get('temperature')}, max_tokens={llm_params.get('max_tokens')}, timeout={llm_params.get('timeout')}{Style.RESET_ALL}")
        
        if current_model != self.llm_client.current_model_alias:
            switch_result = self.llm_client.switch_model(current_model)
            logger.info(f"{Fore.CYAN}[Reload] 模型已切换: {current_model}{Style.RESET_ALL}")
        
        self.file_tool = FileSystemTool(self.agent_config)
        self.shell_tool = ShellTool(self.agent_config)
        self.skill_loader.load_all_skills()
        self.tool_adapter = ToolAdapter(
            self.file_tool, 
            self.shell_tool, 
            self.skill_loader,
            delegation_depth=self.delegation_depth
        )
        self.conversation.reload_prompt()
        
        if self.mcp_manager:
            try:
                self.mcp_manager.disconnect_all_sync()
            except Exception as e:
                logger.debug(f"[Reload] MCP 断开连接时出错（可忽略）: {e}")
        
        AgentInitializer.init_mcp(self)
        AgentInitializer.init_browser(self)
        AgentInitializer.init_memory(self)
        AgentInitializer._start_config_watcher(self)

        # 清除核心工具名称缓存，以便重新加载
        self._core_tool_names_cache = None
        
        logger.info(f"{Fore.GREEN}✅ 所有组件已重载{Style.RESET_ALL}")
    
    def enable_reflection(self, enabled: bool = True, **kwargs) -> None:
        """
        启用/禁用反思机制
        
        功能说明:
            - 控制反思机制的全局开关
            - 支持配置最大反思轮数
            - 支持精细控制各阶段的反思行为
        
        参数:
            enabled: 是否启用反思
            max_rounds: 最大反思轮数（可选）
            decompose: 拆解阶段配置（可选）
            execute: 执行阶段配置（可选）
            summarize: 总结阶段配置（可选）
        
        使用示例:
            >>> agent.enable_reflection(True)  # 全部开启
            >>> agent.enable_reflection(True, max_rounds=3)  # 自定义轮数
            >>> agent.enable_reflection(True, execute={"before": True, "after": False})
        """
        self._reflection_config.enabled = enabled
        
        # 更新配置
        for key, value in kwargs.items():
            if hasattr(self._reflection_config, key):
                setattr(self._reflection_config, key, value)
        
        if enabled:
            # 创建反思引擎
            self._reflection_engine = ReflectionEngine(
                llm_client=self.llm_client,
                config=self._reflection_config
            )
            # 构建 Stage Pipeline
            self._build_pipeline()
            logger.info(f"{Fore.CYAN}✅ 反思机制已启用，最大轮数: {self._reflection_config.max_rounds}{Style.RESET_ALL}")
        else:
            # 禁用反思
            self._reflection_engine = None
            self._stage_pipeline = None
            logger.info(f"{Fore.YELLOW}⚠ 反思机制已禁用{Style.RESET_ALL}")
    
    def _build_pipeline(self) -> None:
        """
        构建 Stage Pipeline
        
        创建三个阶段的 Stage 并组装成 Pipeline
        """
        if not self._reflection_engine:
            return
        
        stages = [
            DecomposeStage(
                agent=self,
                task_decomposer=self.task_decomposer,
                reflection_engine=self._reflection_engine
            ),
            ExecutionStage(
                agent=self,
                reflection_engine=self._reflection_engine
            ),
            SummarizeStage(
                agent=self,
                reflection_engine=self._reflection_engine
            )
        ]
        
        self._stage_pipeline = StagePipeline(stages=stages)
        logger.debug(f"Stage Pipeline 构建完成，包含 {len(stages)} 个阶段")

    def _clear_skill_state(self):
        """
        清理技能状态（注入文档、重复计数等）
        """
        if self.conversation.has_injected_skill():
            self.conversation.clear_injected_document()
        self._last_skill_call = None
        self._last_skill_repeat_count = 0
    
    def _original_chat(self, user_input: str, delegation_depth: Optional[int] = None, images: Optional[List[str]] = None, is_task_step: bool = False) -> dict:
        """
        原始对话方法（不涉及任务拆解）
        
        Args:
            user_input: 用户输入
            delegation_depth: 委托深度（可选）
            images: 图片列表（可选）
            is_task_step: 是否为任务步骤模式（任务拆解模式下的子步骤）
        
        Returns:
            对话结果字典
        """
        if delegation_depth is not None:
            self.delegation_depth = delegation_depth
        
        counter = TokenCounter()
        
        self.conversation.add_message(role="user", content=user_input, images=images)
        
        if not is_task_step and self._auto_save:
            self.conversation.save()
        
        input_summary = user_input[:50] + "..." if len(user_input) > 50 else user_input
        img_info = f", 图片: {len(images)} 张" if images else ""
        logger.info(f"[对话开始] 会话: {self.conversation.session_id}, 输入: {input_summary}{img_info}")
        
        print_conversation_history(self.conversation.get_messages(), max_content_length=88888, print_last_only=True)
        current_tool_calls = 0
        
        tools = self.tool_manager.prepare_tools_with_preprocess(user_input)
   
        logger.info(f"[工具准备] 工具数: {len(tools)}")

        while current_tool_calls < self.max_tool_calls:
            current_tool_calls += 1
            messages = self.conversation.get_messages()
            logger.info(f"{Fore.CYAN}[LLM调用] 第 {current_tool_calls} 轮, 消息数: {len(messages)}{Style.RESET_ALL}")
            
            try:
                response = self.llm_client.chat_completion(
                    messages=messages,
                    tools=tools,
                    stream=False
                )
                
                counter.add_usage(response)
            except Exception as e:
                logger.error(f"[LLM错误] {str(e)}")
                self._clear_skill_state()
                self.conversation.cancel_conversation()
                if not is_task_step and self._auto_save:
                    self.conversation.save()
                
                return counter.build_result(f"大模型调用失败：{str(e)}")

            choice = response.choices[0]
            message = choice.message

            # 提取思考内容：先尝试专用字段，再从 content 中提取 <think> 标签（备用方案）
            reasoning_content = _extract_reasoning_content(message)
            content = message.content or ""
            think_from_content, content = _extract_and_remove_think_tags(content)
            reasoning_content = f"{reasoning_content}\n{think_from_content}" if reasoning_content and think_from_content else (think_from_content or reasoning_content)

            has_tool_calls = hasattr(message, "tool_calls") and message.tool_calls

            if has_tool_calls:
                if reasoning_content:
                    logger.debug(f"[思考过程-工具调用] 模型进行了推理思考:")
                    print(f"\n{Fore.MAGENTA}{'='*60}")
                    print(f"🧠 思考过程 (工具调用阶段):")
                    print(f"{'='*60}{Style.RESET_ALL}")
                    print(f"{Fore.YELLOW}{reasoning_content}{Style.RESET_ALL}")
                    print(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}\n")
            else:
                if reasoning_content:
                    logger.debug(f"[思考过程] 模型进行了推理思考:")
                    print(f"\n{Fore.CYAN}{'='*60}")
                    print(f"🧠 思考过程 (最终回答阶段):")
                    print(f"{'='*60}{Style.RESET_ALL}")
                    print(f"{Fore.YELLOW}{reasoning_content}{Style.RESET_ALL}")
                    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")

            if not self._process_tool_calls(message):
                self.conversation.add_message(role="assistant", content=content)

                print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
                print(f"{Fore.GREEN}🤖 回答:{Style.RESET_ALL}")
                print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
                print(content or "content=None")
                print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}\n")
                
                response_len = len(message.content) if message.content else 0
                logger.info(f"[对话结束] 会话: {self.conversation.session_id}, 回答长度: {response_len}, 耗时: {counter.elapsed_time:.2f}s")

                self._clear_skill_state()

                if is_task_step:
                    with self.conversation._lock:
                        self.conversation._working_messages.clear()
                    logger.debug(f"[任务步骤] 清理临时工作区，不保存到历史")
                else:
                    self.conversation.finalize_conversation()
                    if self._auto_save:
                        self.conversation.save()

                return counter.build_result(message.content or "")

        self._clear_skill_state()

        self.conversation.cancel_conversation()

        if not is_task_step and self._auto_save:
            self.conversation.save()
        
        return counter.build_result("已达到最大工具调用轮数，无法继续执行")

    def _process_tool_calls(self, message: Any) -> bool:
        """
        处理工具调用
        
        Args:
            message: 大模型返回的消息对象
        
        Returns:
            是否处理了工具调用
        """
        if not hasattr(message, "tool_calls") or not message.tool_calls:
            return False
        
        logger.info(f"{Fore.CYAN}检测到工具调用请求，共 {len(message.tool_calls)} 个工具{Style.RESET_ALL}")
        
        tool_names = [tc.function.name for tc in message.tool_calls if tc.function.name]
        logger.info(f"{Fore.CYAN}工具调用: {tool_names}{Style.RESET_ALL}")

        tool_calls_list: List[Dict[str, Any]] = []
        valid_tool_calls = []
        for tc in message.tool_calls:
            if tc.function.name:
                tool_calls_list.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                })
                valid_tool_calls.append(tc)
            else:
                logger.warning(f"{Fore.YELLOW}跳过无效工具调用: name=None, id={tc.id}{Style.RESET_ALL}")
        
        if not valid_tool_calls:
            logger.warning(f"{Fore.YELLOW}所有工具调用都无效，跳过处理{Style.RESET_ALL}")
            return False
        
        assistant_content = message.content or ""
        self.conversation.add_message(
            role="assistant",
            content=assistant_content,
            tool_calls=tool_calls_list
        )
        logger.info(f"{Fore.CYAN}已将 assistant 消息添加到对话历史，包含 {len(tool_calls_list)} 个工具调用{Style.RESET_ALL}")

        invalid_call_count = 0
        max_invalid_calls = 7

        for idx, tool_call in enumerate(valid_tool_calls, 1):
            tool_name = tool_call.function.name
            logger.info(f"{Fore.YELLOW}[{idx}/{len(valid_tool_calls)}] 正在执行工具: {tool_name}{Style.RESET_ALL}")

            invalid_reason = None
            if not tool_call.function.arguments:
                invalid_reason = "工具参数为空"
            else:
                try:
                    args = json.loads(tool_call.function.arguments)
                    if not args or args == {}:
                        invalid_reason = "工具参数为空对象"
                except json.JSONDecodeError:
                    invalid_reason = f"参数格式错误: {tool_call.function.arguments[:50]}"

            if invalid_reason:
                invalid_call_count += 1
                error_msg = f"无效工具调用（{invalid_reason}）。请检查工具名称和参数是否正确。"
                logger.error(f"{Fore.RED}无效工具调用: {invalid_reason}（第 {invalid_call_count} 次）{Style.RESET_ALL}")
                self.conversation.add_tool_result(tool_call.id, tool_name, error_msg)
                
                if invalid_call_count >= max_invalid_calls:
                    final_error = (
                        f"连续 {max_invalid_calls} 次无效工具调用。"
                        f"可能原因：\n"
                        f"1. 工具名称为空或不存在\n"
                        f"2. 必填参数缺失或格式错误\n"
                        f"3. 当前任务可能无法通过工具完成\n"
                        f"请重新描述您的需求，或尝试简化问题。"
                    )
                    logger.error(f"{Fore.RED}连续 {max_invalid_calls} 次无效工具调用，终止循环{Style.RESET_ALL}")
                    self.conversation.add_tool_result(tool_call.id, tool_name, final_error)
                    return True
                continue

            invalid_call_count = 0

            try:
                arguments = json.loads(tool_call.function.arguments)
                logger.debug(f"工具参数: {json.dumps(arguments, ensure_ascii=False)}")
            except json.JSONDecodeError:
                error_msg = f"参数解析失败：{tool_call.function.arguments}"
                logger.error(f"{Fore.RED}工具 {tool_name} 参数解析失败: {error_msg}{Style.RESET_ALL}")
                self.conversation.add_tool_result(tool_call.id, tool_name, error_msg)
                continue

            if tool_name == "get_skill_document":
                skill_name = arguments.get("skill_name", "")
                if skill_name:
                    if not self.conversation.has_injected_skill(skill_name):
                        self.tool_manager.inject_skill_document(skill_name)
                        logger.info(f"{Fore.CYAN}技能 '{skill_name}' 文档已注入 system prompt{Style.RESET_ALL}")
                    else:
                        logger.info(f"{Fore.CYAN}技能 '{skill_name}' 文档已存在，跳过注入{Style.RESET_ALL}")

            
            tool_start_time = time.time()
            
            tool_result = self.tool_adapter.call_tool(tool_name, arguments)
            
            if tool_name == "get_skill_document" and tool_result.get("status") == "success":
                skill_name = tool_result.get("skill_name", "")
                document = tool_result.get("document", "")
                if skill_name and document and not self.conversation.has_injected_skill(skill_name):
                    self.tool_manager.inject_skill_document(skill_name)
                    logger.info(f"{Fore.CYAN}[技能注入] 已将技能 '{skill_name}' 文档注入到 system prompt{Style.RESET_ALL}")
            
            if tool_name == "search_memory" and tool_result.get("status") == "success":
                data = tool_result.get("data", {})
                memories = data.get("memories", [])
                self.conversation.inject_memories(memories)
                if memories:
                    logger.info(f"{Fore.CYAN}[记忆注入] 已将 {len(memories)} 条记忆注入到 system prompt{Style.RESET_ALL}")
                else:
                    logger.info(f"{Fore.CYAN}[记忆注入] 查询结果为空，已清理记忆占位符{Style.RESET_ALL}")
            
            tool_elapsed = time.time() - tool_start_time
            result_status = tool_result.get("status", "unknown")
            
            args_summary = str(arguments)[:100] + "..." if len(str(arguments)) > 100 else str(arguments)
            logger.info(f"[工具调用] {tool_name}, 参数: {args_summary}, 状态: {result_status}, 耗时: {tool_elapsed:.2f}s")
            
            if result_status == "success":
                logger.info(f"{Fore.GREEN}✓ 工具 {tool_name} 执行成功{Style.RESET_ALL}")
            else:
                logger.warning(f"{Fore.RED}✗ 工具 {tool_name} 执行失败: {tool_result.get('message', '未知错误')}{Style.RESET_ALL}")

            self.conversation.add_tool_result(
                tool_call.id,
                tool_name,
                json.dumps(tool_result, ensure_ascii=False, indent=2)
            )

        print_conversation_history(self.conversation.get_messages(), max_content_length=88888,print_last_only=True)
        logger.info(f"{Fore.CYAN}所有工具调用完成，继续生成回答...{Style.RESET_ALL}")
        
        return True

    async def chat_stream(self, user_input: str) -> AsyncGenerator[str, None]:
        """
        模拟流式对话方法。

        参数：
            user_input: 用户输入的对话内容

        返回：
            AsyncGenerator[str, None]: 流式输出生成器（空实现）
        """
        if False:
            yield ""

    def chat(self, user_input: str, delegation_depth: Optional[int] = None, images: Optional[List[str]] = None, reflect: Optional[bool] = None) -> dict:
        """
        非流式对话方法（用于CLI和API调用），支持技能文档动态注入和任务拆解。
        
        新增反思机制支持，可通过 reflect 参数控制是否启用。

        Args:
            user_input: 用户输入
            delegation_depth: 委托深度（覆盖实例级别），用于子代理调用
            images: 图片列表（可选），每项为 URL 或 base64 字符串
            reflect: 是否启用反思机制（可选，None 表示使用全局配置）

        Returns:
            dict: 包含 content, elapsed_time, total_prompt_tokens, total_completion_tokens
        """
        with TokenCounter() as counter:
            if delegation_depth is not None:
                self.delegation_depth = delegation_depth
            
            # 处理单次调用的反思开关
            original_enabled = self._reflection_config.enabled
            if reflect is not None:
                if reflect != self._reflection_config.enabled:
                    self.enable_reflection(reflect)
            
            try:
                # 如果启用了反思机制且 Pipeline 已构建，使用 Stage Pipeline 执行
                if self._reflection_config.enabled and self._stage_pipeline:
                    logger.info(f"{Fore.CYAN}[StagePipeline] 使用反思架构执行{Style.RESET_ALL}")
                    return self._chat_with_pipeline(user_input, images, counter)
                
            finally:
                # 恢复原始配置
                if reflect is not None and reflect != original_enabled:
                    self.enable_reflection(original_enabled)
    
    def _chat_with_pipeline(self, user_input: str, images: Optional[List[str]], counter: TokenCounter) -> dict:
        """
        使用 Stage Pipeline 执行对话（反思架构）
        
        Args:
            user_input: 用户输入
            images: 图片列表（已废弃，建议使用 attachments）
            counter: TokenCounter 实例
            
        Returns:
            dict: 执行结果
        """
        try:
            # 用户消息直接保存到 history，确保即使执行失败也能持久化
            with self.conversation._lock:
                self.conversation.history.append({"role": "user", "content": user_input})
            if self._auto_save:
                self.conversation.save()
            
            # 获取能力标签
            ability_tags = []
            if self.memory_system:
                ability_tags = self.memory_system.get_all_capabilities() or []

            if not ability_tags:
                ability_tags = ["llm_response", "文件读取", "文件写入", "命令执行", "网络搜索"]
            
            # 创建初始上下文
            context = StageContext(user_input=user_input)
            context.set("ability_tags", ability_tags)
            
            # 构建附件元信息（用于任务拆解阶段）
            if images:
                attachments_meta = []
                for img in images:
                    attachments_meta.append({
                        "type": "image",
                        "filename": "image.jpg",
                        "content_type": "image/jpeg",
                        "size": len(img) if img else 0
                    })
                context.set("attachments", attachments_meta)
                # 同时保存完整图片数据（用于执行阶段）
                context.set("images", images)
            
            # 执行 Pipeline
            result = self._stage_pipeline.execute(context)
            
            if result.success:
                # 获取最终总结结果
                # result.data 是 context.data，包含所有阶段的结果
                # summarize_result 的结构是 {"summarize_result": "实际内容"}
                summarize_data = result.data.get("summarize_result", {})
                if isinstance(summarize_data, dict):
                    summary = summarize_data.get("summarize_result", "任务执行完成")
                else:
                    summary = summarize_data if summarize_data else "任务执行完成"
                
                # 添加到对话历史
                self.conversation.add_message(role="assistant", content=summary)
                self.conversation.finalize_conversation(save_user_message=False)
                
                if self._auto_save:
                    self.conversation.save()
                
                # 累加各阶段的 token 使用量
                decompose_prompt = result.data.get("decompose_prompt_tokens", 0)
                decompose_completion = result.data.get("decompose_completion_tokens", 0)
                execution_prompt = result.data.get("execution_prompt_tokens", 0)
                execution_completion = result.data.get("execution_completion_tokens", 0)
                
                total_prompt = decompose_prompt + execution_prompt
                total_completion = decompose_completion + execution_completion
                
                counter.add_tokens(total_prompt, total_completion)

                logger.info(f"{Fore.CYAN}[StagePipeline] Token 统计 - 拆解: {decompose_prompt}/{decompose_completion}, 执行: {execution_prompt}/{execution_completion}, 总计: {total_prompt}/{total_completion}{Style.RESET_ALL}")

                # 构建结果并添加上下文使用率信息
                result_dict = counter.build_result(summary)

                # 计算上下文使用率（与旧架构保持一致）
                context_window = self.llm_client.get_context_window()
                history_tokens = self.llm_client.count_tokens(self.conversation.get_messages())
                context_usage_percent = (history_tokens / context_window * 100) if context_window > 0 else 0

                result_dict["context_window"] = context_window
                result_dict["context_usage_percent"] = context_usage_percent

                return result_dict
            else:
                # 执行失败
                error_msg = result.message or "Pipeline 执行失败"
                logger.error(f"{Fore.RED}[StagePipeline] 执行失败: {error_msg}{Style.RESET_ALL}")
                return counter.build_result(f"执行失败: {error_msg}")
                
        except Exception as e:
            logger.error(f"{Fore.RED}[StagePipeline] 异常: {e}{Style.RESET_ALL}")
            return counter.build_result(f"执行异常: {str(e)}")
    

    def _execute_by_task_type(self, task_tree: Dict, user_input: str, counter: TokenCounter, skip_summarize: bool = False, images: Optional[List[str]] = None) -> dict:
        """
        根据任务类型执行不同流程（供 ExecutionStage 调用）
        
        Args:
            task_tree: 任务树字典
            user_input: 用户输入
            counter: TokenCounter 实例
            skip_summarize: 是否跳过汇总阶段（Pipeline 模式下由 SummarizeStage 负责）
            images: 图片列表（可选）
        
        Returns:
            执行结果字典
        """
        return self.task_executor.execute_by_task_type(task_tree, user_input, counter, skip_summarize, images=images)