#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :agent_task_executor.py
# @Time      :2026/03/12
# @Author    :Ficus

"""
Agent 任务执行器模块

该模块负责任务的拆解、执行和管理，包括任务树的执行、步骤执行、结果汇总等功能。
"""
import json
import re
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Set

from colorama import Fore, Style
from loguru import logger

from agent.core.agent_utils import _extract_and_remove_think_tags, _extract_reasoning_content
from agent.core.token_counter import TokenCounter

if TYPE_CHECKING:
    from agent.core.agent import Agent


class TaskExecutor:
    """
    任务执行器，负责任务的拆解、执行和管理。
    
    功能说明:
        - 检查未完成任务
        - 获取已完成步骤的结果
        - 格式化前置结果
        - 总结执行结果
        - 根据任务类型执行不同流程
        - 恢复未完成任务
        - 执行任务树
        - 汇总任务结果
        - 准备工具列表
        - 执行具体步骤
    
    核心方法:
        - check_pending_task: 检查未完成任务
        - get_completed_results: 获取已完成步骤结果
        - format_previous_results: 格式化前置结果
        - summarize_result: 总结单个结果
        - execute_by_task_type: 根据任务类型执行
        - resume_task: 恢复未完成任务
        - execute_task_tree: 执行任务树（新任务）
        - execute_task_with_tree: 执行任务树核心逻辑
        - summarize_task_results: 汇总任务结果
        - prepare_tools_for_ability_match: 根据能力准备工具
        - execute_step_with_tools: 执行需要工具的步骤
        - get_next_step_desc: 获取下一步骤描述
    
    配置项:
        - agent: Agent 实例引用
    """
    
    def __init__(self, agent: "Agent"):
        """
        初始化任务执行器。
        
        Args:
            agent: Agent 实例
        """
        self.agent = agent
    
    def check_pending_task(self) -> Optional[Dict]:
        """
        检查是否有未完成任务（代码判断）
        
        Returns:
            未完成任务信息字典，无则返回 None
        """
        if not self.agent.heartbeat_manager:
            return None
        
        pending_info = self.agent.heartbeat_manager.has_pending_task()
        if not pending_info:
            return None
        
        task_id = pending_info.get("task_id")
        if not task_id:
            return None
        
        task_tree = self.agent.task_tree_manager.load(task_id)
        if not task_tree:
            return None
        
        heartbeat = self.agent.heartbeat_manager.load()
        if not heartbeat:
            return None
        
        completed_steps = heartbeat.get("completed_steps", [])
        current_step = self.agent.task_tree_manager.get_current_step(task_id, heartbeat)
        
        return {
            "task_id": task_id,
            "task_goal": task_tree.get("task_goal", ""),
            "progress": f"{len(completed_steps)}/{heartbeat.get('total_steps', 0)}",
            "current_step": current_step,
            "status": pending_info.get("status", "")
        }

    def get_completed_results(self, task_id: str) -> List[Dict]:
        """
        获取已完成步骤的结果（用于执行阶段注入）
        
        Args:
            task_id: 任务 ID
        
        Returns:
            已完成步骤结果列表
        """
        heartbeat = self.agent.heartbeat_manager.load()
        if not heartbeat:
            return []
        
        completed_steps = set(heartbeat.get("completed_steps", []))
        if not completed_steps:
            return []
        
        results_data = self.agent.task_tree_manager.load_results(task_id)
        if not results_data:
            return []
        
        completed_results = []
        for result in results_data.get("results", []):
            if result.get("step_id") in completed_steps:
                completed_results.append({
                    "step_id": result.get("step_id"),
                    "step_desc": result.get("step_desc", ""),
                    "tool_name": result.get("tool_name", ""),
                    "summary": self.summarize_result(result.get("result", {}))
                })
        
        return completed_results

    def format_previous_results(self, task_id: str, completed_steps: Set[str]) -> str:
        """
        格式化前置结果为简洁字符串
        
        Args:
            task_id: 任务 ID
            completed_steps: 已完成步骤 ID 集合
        
        Returns:
            格式化的前置结果字符串
        """
        if not completed_steps:
            return ""
        
        results_data = self.agent.task_tree_manager.load_results(task_id)
        if not results_data:
            return ""
        
        formatted = []
        for result in results_data.get("results", []):
            step_id = result.get("step_id", "")
            if step_id in completed_steps:
                summary = self.summarize_result(result.get("result", {}), max_length=100)
                formatted.append(f"[{step_id}] {summary}")
        
        return "\n".join(formatted) if formatted else ""

    def summarize_result(self, result: Dict, max_length: int = 200) -> str:
        """
        总结执行结果
        
        Args:
            result: 执行结果字典
            max_length: 最大长度
        
        Returns:
            结果摘要字符串
        """
        if not result:
            return "无结果"
        
        if isinstance(result, dict):
            if "content" in result:
                content = str(result["content"])
                return content[:max_length] + "..." if len(content) > max_length else content
            if "status" in result:
                return f"状态: {result['status']}"
        
        return str(result)[:max_length]

    def execute_by_task_type(self, task_tree: Dict, user_input: str, counter: TokenCounter, skip_summarize: bool = False, images: Optional[List[str]] = None) -> dict:
        """
        根据 task_type 执行不同流程
        
        Args:
            task_tree: 任务树字典（包含 prompt_tokens 和 completion_tokens）
            user_input: 用户输入
            counter: TokenCounter 实例
            skip_summarize: 是否跳过汇总阶段（Pipeline 模式下由 SummarizeStage 负责）
            images: 图片列表（可选）
        
        Returns:
            执行结果字典
        """
        task_type = task_tree.get("task_type", "new_task")
        
        if task_type == "continue":
            return self.resume_task(counter, skip_summarize)
        
        return self.execute_task_tree(task_tree, user_input, counter, skip_summarize, images=images)

    def resume_task(self, counter: TokenCounter, skip_summarize: bool = False) -> dict:
        """
        继续执行未完成任务
        
        Args:
            counter: TokenCounter 实例
            skip_summarize: 是否跳过汇总阶段
        
        Returns:
            执行结果字典
        """
        if not self.agent.heartbeat_manager or not self.agent.task_tree_manager:
            return counter.build_result("任务拆解模块未初始化")
        
        heartbeat = self.agent.heartbeat_manager.load()
        if not heartbeat:
            return counter.build_result("没有未完成的任务")
        
        task_id = heartbeat.get("task_id")
        task_tree = self.agent.task_tree_manager.load(task_id)
        
        if not task_tree:
            return counter.build_result("任务树加载失败")
        
        logger.info(f"{Fore.CYAN}[断点续跑] 恢复任务: {task_id}{Style.RESET_ALL}")
        
        return self.execute_task_with_tree(task_tree, task_id, counter, skip_summarize)

    def execute_task_tree(self, task_tree: Dict, user_input: str, counter: TokenCounter, skip_summarize: bool = False, images: Optional[List[str]] = None) -> dict:
        """
        执行任务树（新任务）
        
        如果有未完成任务，会先放弃旧任务再创建新任务。
        
        Args:
            task_tree: 任务树字典（包含 prompt_tokens 和 completion_tokens）
            user_input: 用户输入
            counter: TokenCounter 实例
            skip_summarize: 是否跳过汇总阶段
            images: 图片列表（可选）
        
        Returns:
            执行结果字典
        """
        counter.add_tokens(
            task_tree.get("prompt_tokens", 0),
            task_tree.get("completion_tokens", 0)
        )
        
        if not self.agent.task_tree_manager or not self.agent.heartbeat_manager:
            logger.warning(f"{Fore.YELLOW}[任务执行] 任务拆解模块未初始化，回退到普通对话{Style.RESET_ALL}")
            result = self.agent._original_chat(user_input, images=images)
            counter.add_tokens(
                result.get("total_prompt_tokens", 0),
                result.get("total_completion_tokens", 0)
            )
            return counter.build_result(result.get("content", ""))
        
        heartbeat = self.agent.heartbeat_manager.load()
        if heartbeat and heartbeat.get("task_id"):
            old_task_id = heartbeat.get("task_id")
            self.agent.task_tree_manager.update_task_status(old_task_id, "abandoned")
            self.agent.heartbeat_manager.clear()
            logger.info(f"{Fore.CYAN}[任务切换] 已放弃旧任务: {old_task_id}{Style.RESET_ALL}")
        
        task_id = self.agent.task_tree_manager.generate_task_id()
        
        self.agent.task_tree_manager.save(task_id, task_tree)
        self.agent.heartbeat_manager.init(task_id, task_tree)
        
        logger.info(f"{Fore.CYAN}[任务执行] 创建新任务: {task_id}{Style.RESET_ALL}")
        
        return self.execute_task_with_tree(task_tree, task_id, counter, skip_summarize, images=images)

    def execute_task_with_tree(self, task_tree: Dict, task_id: str, counter: TokenCounter, skip_summarize: bool = False, images: Optional[List[str]] = None) -> dict:
        """
        执行任务树（核心执行逻辑）
        
        Args:
            task_tree: 任务树字典
            task_id: 任务 ID
            counter: TokenCounter 实例
            skip_summarize: 是否跳过汇总阶段（Pipeline 模式下由 SummarizeStage 负责）
            images: 图片列表（可选，仅在第一个步骤时使用）
        
        Returns:
            执行结果字典
        """
        while True:
            heartbeat = self.agent.heartbeat_manager.load()
            if not heartbeat:
                break
            
            if heartbeat.get("status") == "completed":
                logger.info(f"{Fore.GREEN}[任务完成] 任务 {task_id} 已完成{Style.RESET_ALL}")
                break
            
            completed_steps = heartbeat.get("completed_steps", [])
            current_step = self.agent.task_tree_manager.get_runnable_step(task_id, completed_steps)
            
            if not current_step:
                logger.info(f"{Fore.CYAN}[任务执行] 无可执行步骤，任务可能已完成{Style.RESET_ALL}")
                break
            
            step_id = current_step.get("step_id")
            required_abilities = current_step.get("required_abilities", [])
            
            if "continue" in required_abilities:
                self.agent.heartbeat_manager.start_step(step_id)
                self.agent.heartbeat_manager.complete_step(step_id)
                self.agent.task_tree_manager.update_step_status(task_id, step_id, "completed")
                continue
            
            task_context = {
                "task_goal": task_tree.get("task_goal", ""),
                "total_steps": task_tree.get("total_steps", 0),
                "completed_steps": len(completed_steps),
                "current_step": current_step,
                "next_step_desc": self.get_next_step_desc(task_tree, completed_steps)
            }
            
            self.agent.conversation.inject_task_context(task_context)
            
            self.agent.heartbeat_manager.start_step(step_id)
            
            tools = self.prepare_tools_for_ability_match(required_abilities)
            step_index = len(completed_steps) + 1
            previous_results = self.format_previous_results(task_id, set(completed_steps))
            
            # 只在第一个步骤且从未执行过时传递图片
            # 检查心跳中是否有任何步骤记录（包括失败的）
            started_steps = heartbeat.get("started_steps", [])
            is_first_step_ever = step_index == 1 and len(started_steps) == 0
            step_images = images if is_first_step_ever else None
            
            step_result = self.execute_step_with_tools(
                current_step, 
                tools, 
                task_tree,
                step_index,
                previous_results,
                images=step_images
            )
            
            counter.add_tokens(
                step_result.get("prompt_tokens", 0),
                step_result.get("completion_tokens", 0)
            )
            
            if step_result.get("success"):
                self.agent.task_tree_manager.update_step_status(task_id, step_id, "completed")
                self.agent.heartbeat_manager.complete_step(step_id)
                self.agent.task_tree_manager.save_step_result(
                    task_id, 
                    step_id, 
                    step_result.get("tool_name", ""),
                    step_result.get("arguments", {}),
                    step_result.get("result", {})
                )
            else:
                self.agent.task_tree_manager.increment_retry(task_id, step_id)
                self.agent.task_tree_manager.update_step_status(
                    task_id, 
                    step_id, 
                    "failed",
                    step_result.get("error")
                )
                self.agent.heartbeat_manager.fail_step(step_id, step_result.get("error", "未知错误"))
                logger.warning(f"{Fore.YELLOW}[任务执行] 步骤 {step_id} 失败: {step_result.get('error')}{Style.RESET_ALL}")
            
            with self.agent.conversation._lock:
                self.agent.conversation._working_messages.clear()
            
            self.agent.conversation.clear_task_context()
            self.agent.conversation.clear_injected_document()
        
        task_tree = self.agent.task_tree_manager.load(task_id)
        final_status = task_tree.get("status", "unknown") if task_tree else "unknown"
        
        if final_status in ["completed", "partial_completed"]:
            if skip_summarize:
                logger.info(f"{Fore.CYAN}[任务执行] Pipeline 模式，跳过汇总，返回 task_id: {task_id}{Style.RESET_ALL}")
                return counter.build_result_with_task_id(
                    content="",
                    task_id=task_id,
                    final_status=final_status,
                    total_prompt_tokens=counter.total_prompt_tokens,
                    total_completion_tokens=counter.total_completion_tokens
                )
            
            self.agent.heartbeat_manager.clear()
            
            summary_result = self.summarize_task_results(task_id, task_tree, counter)
            
            if final_status == "partial_completed":
                failed_steps = [s for s in task_tree.get("task_tree", []) if s.get("status") == "failed"]
                failed_info = "\n".join([f"- {s.get('step_id')}: {s.get('error_message', '未知错误')}" for s in failed_steps])
                summary_result["content"] = f"{summary_result.get('content', '')}\n\n⚠️ [执行]部分步骤执行失败:\n{failed_info}"
            
            self.agent.conversation.history.append({"role": "assistant", "content": summary_result.get("content", "")})
            logger.info(f"{Fore.CYAN}[Legacy模式] assistant 消息已直接保存到 history{Style.RESET_ALL}")
            
            if self.agent._auto_save:
                self.agent.conversation.save()
            
            return summary_result
        else:
            logger.warning(f"{Fore.YELLOW}[任务执行] 任务执行中断，状态: {final_status}，用户消息已保存{Style.RESET_ALL}")
            return counter.build_result(f"任务执行中断，状态: {final_status}")

    def summarize_task_results(self, task_id: str, task_tree: Dict, counter: TokenCounter) -> dict:
        """
        汇总任务执行结果
        
        Args:
            task_id: 任务 ID
            task_tree: 任务树
            counter: TokenCounter 实例
        
        Returns:
            汇总结果字典
        """
        results_data = self.agent.task_tree_manager.load_results(task_id)
        
        if not results_data:
            return counter.build_result(f"任务执行完成: {task_tree.get('task_goal', '')}")
        
        all_step_contents = []
        all_results = []
        for step_result in results_data.get("results", []):
            result = step_result.get("result", {})
            content = result.get("content", "")
           
            
            if content:
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict):
                        actual_content = parsed.get("content", "")
                        if actual_content:
                            all_step_contents.append(f"[{step_result.get('step_id', '')}] {actual_content}")
                            all_results.append(actual_content)
                        else:
                            all_step_contents.append(f"[{step_result.get('step_id', '')}] {content}")
                            all_results.append(content)
                            
                    else:
                        all_step_contents.append(f"[{step_result.get('step_id', '')}] {content}")
                        all_results.append(content)
                except (json.JSONDecodeError, TypeError):
                    all_step_contents.append(f"[{step_result.get('step_id', '')}] {content}")
                    all_results.append(content)
        
        if not all_step_contents:
            return counter.build_result(f"任务执行完成: {task_tree.get('task_goal', '')}")
        
        task_goal = task_tree.get("task_goal", "")
        summary_prompt = f"""用户的原始请求：{task_goal}
            执行结果：
            {chr(10).join(all_step_contents)}
            
            请根据用户的原始请求来决定回复方式：
            - 如果用户要求简短回复，请简洁回答
            - 如果用户要求详细报告，请详细说明
            - 如果用户要求总结，请给出总结
            - 如果用户没有特别要求，用自然友好的语气总结
            
            直接回复用户，不要解释你的回复方式。"""
        
        try:
            # 如果只有一步，直接返回内容
            
            if len(all_step_contents) > 1:
                logger.debug(f"\n{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}")
                logger.debug(f"{Fore.MAGENTA}📤 [任务汇总] 请求消息:{Style.RESET_ALL}")
                logger.debug(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}")
                logger.debug(f"{Fore.YELLOW}{summary_prompt}{Style.RESET_ALL}")
                logger.debug(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}\n")
        
                response = self.agent.llm_client.chat_completion(
                messages=[{"role": "user", "content": summary_prompt}],
                stream=False)
                counter.add_usage(response)

                # 提取思考内容：先尝试专用字段，再从 content 中提取 <think> 标签（备用方案）
                message = response.choices[0].message
                reasoning_content = _extract_reasoning_content(message)
                summary_content = message.content or ""
                think_from_content, summary_content = _extract_and_remove_think_tags(summary_content)
                reasoning_content = f"{reasoning_content}\n{think_from_content}" if reasoning_content and think_from_content else (think_from_content or reasoning_content)

                # 打印思考内容（如果有）
                if reasoning_content:
                    logger.debug(f"[思考过程-任务汇总] 模型进行了推理思考:")
                    print(f"\n{Fore.CYAN}{'='*60}")
                    print(f"🧠 思考过程 (任务汇总阶段):")
                    print(f"{'='*60}{Style.RESET_ALL}")
                    print(f"{Fore.YELLOW}{reasoning_content}{Style.RESET_ALL}")
                    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
            else:
                summary_content = re.sub(r'^\[step_\d+\]\s*', '', all_results[0] or "")
                
            logger.debug(f"[任务汇总] 生成总结成功")
            print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
            print(f"{Fore.GREEN}🤖 任务汇总回答:{Style.RESET_ALL}")
            print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
            print(summary_content)
            print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}\n")
            
            return counter.build_result(summary_content)
        except Exception as e:
            logger.error(f"[任务汇总] 生成总结失败: {e}")
            return counter.build_result(f"任务执行完成: {task_goal}\n\n执行结果:\n" + "\n".join(all_step_contents))

    def prepare_tools_for_ability_match(self, required_abilities: List[str]) -> List[Dict]:
        """
        根据能力需求准备工具列表
        
        Args:
            required_abilities: 所需能力列表
        
        Returns:
            工具定义列表
        """
        core_tools = self.agent.tool_manager.get_core_tools()
        logger.debug(f"[工具准备] _get_core_tools 返回 {len(core_tools)} 个工具, memory_system={self.agent.memory_system is not None}")
        
        # if self.agent.memory_system:
        #     for ability in required_abilities:
        #         if ability not in ["llm_response", "continue"]:
        #             logger.info(f"[工具准备] 为能力 '{ability}' 调用 discover 搜索工具")
        #             discover_result = self.agent.tool_adapter.call_tool("discover", {
        #                 "query": ability,
        #                 "resource_type": "tool"
        #             })
        #             logger.debug(f"[预工具准备] discover 返回: status={discover_result.get('status')}")
                    
        #             if discover_result.get("status") == "success":
        #                 tools = discover_result.get("data", {}).get("tools", [])
        #                 # 处理工具名称：优先从 function.name 获取，否则从 name 获取
        #                 tool_names = []
        #                 for t in tools:
        #                     func_def = t.get("function", t)
        #                     name = func_def.get("name") if isinstance(func_def, dict) else t.get("name")
        #                     tool_names.append(name)
        #                 logger.debug(f"[工具准备] discover 找到 {len(tools)} 个工具: {tool_names}")
        #                 for tool in tools:
        #                     # 处理工具名称：优先从 function.name 获取，否则从 name 获取
        #                     func_def = tool.get("function", tool)
        #                     tool_name = func_def.get("name") if isinstance(func_def, dict) else tool.get("name")
        #                     if tool_name and tool_name not in [t["function"]["name"] for t in core_tools]:
        #                         if tool_name in self.agent.tool_adapter.tools:
        #                             tool_info = self.agent.tool_adapter.tools[tool_name]
        #                             core_tools.append({
        #                                 "type": "function",
        #                                 "function": {
        #                                     "name": tool_name,
        #                                     "description": tool_info.get("description", ""),
        #                                     "parameters": tool_info.get("parameters", {})
        #                                 }
        #                             })
        #                             logger.info(f"[工具准备] 已添加工具: {tool_name}")
                                    
        #                             if tool_name.startswith("skill_"):
        #                                 skill_name = tool_name[6:]
        #                                 if not self.agent.conversation.has_injected_skill(skill_name):
        #                                     self.agent.tool_manager.inject_skill_document(skill_name)
        
        
        logger.debug(f"[工具准备] 最终返回 {len(core_tools)} 个工具")
        return core_tools

    def execute_step_with_tools(
        self, 
        current_step: Dict, 
        tools: List[Dict], 
        task_tree: Dict,
        step_index: int = 1,
        previous_results: str = "",
        images: Optional[List[str]] = None
    ) -> dict:
        """
        执行需要工具的步骤
        
        Args:
            current_step: 当前步骤
            tools: 工具列表
            task_tree: 任务树
            step_index: 当前步骤序号（从1开始）
            previous_results: 前置结果摘要
            images: 图片列表（可选，仅在第一个步骤时传递）
        
        Returns:
            执行结果字典，包含 success, content, prompt_tokens, completion_tokens 等
        """
        step_desc = current_step.get("step_desc", "")
        step_id = current_step.get("step_id", "unknown")
        total_steps = task_tree.get("total_steps", 0)
        task_goal = task_tree.get("task_goal", "")
        # 获取能力标签
        abilities = current_step.get("required_abilities", [])
        
            
        # 前置结果为空时显示引导语
        previous_results_display = previous_results if previous_results else ""
        
        step_prompt = f"""【总体目标】{task_goal}
【当前步骤】{step_id}（第{step_index}/{total_steps}步）
【本步任务】{step_desc}
【建议能力标签】{abilities}

⚠️ 重要规则：
1. 你只需要执行【本步任务】，不要执行后续步骤
2. 根据【本步任务】，判断是否需要调用工具，调用工具可参考【建议能力标签】和自己认为需要的工具关键词
3. 不要添加"思考："、"推理："等前缀
4. 当本步任务完成后，在回答末尾添加 [STEP_DONE] 标记
5. 输出的内容content必须有值，否则系统会崩溃

【前置结果】{previous_results_display}"""
        
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}📍 开始执行步骤: {step_id}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}📝 步骤描述: {step_desc[:100]}{'...' if len(step_desc) > 100 else ''}{Style.RESET_ALL}")
        if images:
            print(f"{Fore.CYAN}📷 图片数量: {len(images)}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
        
        self.agent.conversation.add_message(role="user", content=step_prompt, images=images)
        
        current_tool_calls = 0
        max_step_tool_calls = self.agent.max_tool_calls
        counter = TokenCounter()
        has_called_tool = False
        empty_response_count = 0
        max_empty_responses = 3
        
        while current_tool_calls < max_step_tool_calls:
            current_tool_calls += 1
            
            try:
                messages = self.agent.conversation.get_messages()
                logger.info(f"{Fore.CYAN}[步骤执行] 第 {current_tool_calls} 轮, 消息数: {len(messages) if messages else 0}{Style.RESET_ALL}")
                logger.debug(f"[步骤执行] 工具数: {len(tools) if tools else 0}")
                
                print(f"\n{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}")
                print(f"{Fore.MAGENTA}📤 [{step_id}] 请求消息:{Style.RESET_ALL}")
                print(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}")
                print(messages)
                print(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}\n")
                
                # 判断步骤是否需要工具（用于后续提示）
                required_abilities = current_step.get("required_abilities", [])
                needs_tool = "llm_response" not in required_abilities and "continue" not in required_abilities
                
                # 始终使用 auto 模式，让模型自主决定是否调用工具
                tool_choice = "auto"
                
                logger.info(f"{Fore.CYAN}[步骤执行] tool_choice={tool_choice}, needs_tool={needs_tool}, tools数量={len(tools) if tools else 0}{Style.RESET_ALL}")
                
                response = self.agent.llm_client.chat_completion(
                    messages=messages,
                    tools=tools,
                    stream=False,
                    tool_choice=tool_choice
                )
                
                # 调试：检查模型响应中是否有 tool_calls
                message = response.choices[0].message
                has_tool_calls = hasattr(message, "tool_calls") and message.tool_calls
                logger.info(f"{Fore.CYAN}[步骤执行] 模型响应 has_tool_calls={has_tool_calls}, content长度={len(message.content) if message.content else 0}{Style.RESET_ALL}")
                
                counter.add_usage(response)
                

                # 提取思考内容：先尝试专用字段，再从 content 中提取 <think> 标签（备用方案）
                reasoning_content = _extract_reasoning_content(message)
                content = message.content or ""
                think_from_content, content = _extract_and_remove_think_tags(content)
                reasoning_content = f"{reasoning_content}\n{think_from_content}" if reasoning_content and think_from_content else (think_from_content or reasoning_content)

                
                if reasoning_content:
                    print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
                    print(f"{Fore.CYAN}🧠 [{step_id}] 思考过程:{Style.RESET_ALL}")
                    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
                    print(reasoning_content)
                    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")

                if not self.agent._process_tool_calls(message):
                    
                    if "[STEP_FAILED]" in content:
                        final_content = content.replace("[STEP_FAILED]", "").strip()
                        logger.warning(f"{Fore.YELLOW}[步骤执行] 模型报告任务失败{Style.RESET_ALL}")
                        return {
                            "success": False,
                            "error": final_content or "任务执行失败",
                            "content": final_content,
                            "prompt_tokens": counter.total_prompt_tokens,
                            "completion_tokens": counter.total_completion_tokens
                        }
                    
                    if "[STEP_DONE]" in content:
                        final_content = content.replace("[STEP_DONE]", "").strip()
                        self.agent.conversation.add_message(role="assistant", content=content)
                        logger.info(f"{Fore.GREEN}[步骤执行] 模型报告任务完成{Style.RESET_ALL}")
                        print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
                        print(f"{Fore.GREEN}🤖 [{step_id}] 步骤回答:{Style.RESET_ALL}")
                        print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
                        print(final_content)
                        print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}\n")
                        return {
                            "success": True,
                            "content": final_content,
                            "tool_name": "",
                            "arguments": {},
                            "result": {"content": final_content},
                            "prompt_tokens": counter.total_prompt_tokens,
                            "completion_tokens": counter.total_completion_tokens
                        }
                    
                    if needs_tool and not has_called_tool:
                        # 步骤需要工具但模型尚未调用，添加提示引导模型使用工具
                        warning_msg = "⚠️ 本步骤需要使用工具来完成任务。请查看可用的工具列表，选择合适的工具进行调用。工具执行结果会返回给你，你可以根据结果继续下一步操作。"
                        logger.warning(f"{Fore.YELLOW}[步骤执行] 步骤需要工具但模型未调用，添加提示引导{Style.RESET_ALL}")
                        
                        self.agent.conversation.add_message(role="assistant", content=content or reasoning_content or "")
                        self.agent.conversation.add_message(role="user", content=warning_msg)
                        continue
                    
                    if has_called_tool:
                        # 已经调用过工具，但模型返回空内容且没有标记完成
                        # 尝试重试，给模型提示让它继续生成
                        empty_response_count += 1
                        
                        if empty_response_count < max_empty_responses:
                            retry_msg = f"⚠️ 你刚才调用了工具，但返回的内容为空。请根据工具执行结果继续完成任务，并在完成后添加 [STEP_DONE] 标记。当前是第 {empty_response_count} 次重试，最多 {max_empty_responses} 次。"
                            logger.warning(f"{Fore.YELLOW}[步骤执行] 工具已调用但返回空内容，第 {empty_response_count}/{max_empty_responses} 次重试{Style.RESET_ALL}")
                            
                            self.agent.conversation.add_message(role="assistant", content=content or reasoning_content or "")
                            self.agent.conversation.add_message(role="user", content=retry_msg)
                            continue
                        else:
                            # 超过最大重试次数，使用可用内容或返回错误
                            final_content = content or reasoning_content or ""
                            if final_content:
                                logger.info(f"{Fore.GREEN}[步骤执行] 达到最大重试次数，使用可用内容作为回复{Style.RESET_ALL}")
                                return {
                                    "success": True,
                                    "content": final_content,
                                    "tool_name": "",
                                    "arguments": {},
                                    "result": {"content": final_content},
                                    "prompt_tokens": counter.total_prompt_tokens,
                                    "completion_tokens": counter.total_completion_tokens
                                }
                            else:
                                logger.warning(f"{Fore.YELLOW}[步骤执行] 达到最大重试次数且无可用内容，终止执行{Style.RESET_ALL}")
                                return {
                                    "success": False,
                                    "error": f"工具调用后模型连续 {max_empty_responses} 次返回空响应，无法继续执行任务。请检查工具执行结果或重新描述需求。",
                                    "content": "模型返回空内容",
                                    "prompt_tokens": counter.total_prompt_tokens,
                                    "completion_tokens": counter.total_completion_tokens
                                }
                    
                    self.agent.conversation.add_message(role="assistant", content=content)
                    
                    final_content = content
                    if not final_content and reasoning_content:
                        final_content = reasoning_content
                        logger.info(f"[步骤执行] content为空，使用思考内容作为兜底")
                    
                    print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
                    print(f"{Fore.GREEN}🤖 [{step_id}] 步骤回答:{Style.RESET_ALL}")
                    print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
                    print(final_content)
                    print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}\n")
                    
                    return {
                        "success": True,
                        "content": final_content,
                        "tool_name": "",
                        "arguments": {},
                        "result": {"content": final_content},
                        "prompt_tokens": counter.total_prompt_tokens,
                        "completion_tokens": counter.total_completion_tokens
                    }
                
                has_called_tool = True
                    
            except Exception as e:
                logger.error(f"{Fore.RED}[步骤执行] 工具调用失败: {e}{Style.RESET_ALL}")
                return {
                    "success": False,
                    "error": str(e),
                    "prompt_tokens": counter.total_prompt_tokens,
                    "completion_tokens": counter.total_completion_tokens
                }
        
        return {
            "success": False,
            "error": "达到最大工具调用次数",
            "prompt_tokens": counter.total_prompt_tokens,
            "completion_tokens": counter.total_completion_tokens
        }

    def get_next_step_desc(self, task_tree: Dict, completed_steps: List[str]) -> str:
        """
        获取下一步骤描述
        
        Args:
            task_tree: 任务树
            completed_steps: 已完成步骤列表
        
        Returns:
            下一步骤描述
        """
        completed_set = set(completed_steps)
        steps = task_tree.get("task_tree", [])
        
        found_current = False
        for step in steps:
            if step["step_id"] in completed_set:
                continue
            if found_current:
                return step.get("step_desc", "")
            found_current = True
        
        return "无"
