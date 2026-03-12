#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :handlers.py
# @Time      :2026/03/07
# @Author    :Ficus

"""
消息处理器模块

该模块定义消息处理器，支持单播/多播/广播路由模式。
"""
import asyncio
import time
from typing import List, Optional, TYPE_CHECKING
from loguru import logger

from agent.core.messaging.message import Message, MessageResponse, StreamResponse

if TYPE_CHECKING:
    from agent.core.agent import Agent
    from agent.registry import AgentRegistry


class ChatHandler:
    """
    对话处理器 - 支持单播/多播/广播
    
    功能说明:
        - 处理聊天类型消息
        - 支持单播、多播、广播三种路由模式
        - 多 Agent 并行处理时聚合响应
        - 支持异步处理同步 Agent.chat 方法
    
    核心方法:
        - handle: 处理消息
        - _get_target_agents: 获取目标 Agent 列表
        - _handle_single: 处理单个 Agent
        - _handle_multiple: 并行处理多个 Agent
    
    路由优先级:
        1. broadcast=True → 所有 Agent
        2. target_agents=["a", "b"] → 指定多个 Agent
        3. target_agent="a" → 指定单个 Agent
        4. 默认 → 默认 Agent
    """
    
    def __init__(
        self, 
        agent_id: str, 
        agent: "Agent",
        registry: Optional["AgentRegistry"] = None
    ):
        """
        初始化对话处理器
        
        Args:
            agent_id: Agent ID
            agent: Agent 实例
            registry: Agent 注册中心（可选，用于多播/广播）
        """
        self._agent_id = agent_id
        self._agent = agent
        self._registry = registry
        logger.debug(f"[ChatHandler] 初始化处理器，Agent ID: {agent_id}, 有注册中心: {registry is not None}")
    
    def _get_target_agents(self, message: Message) -> List["Agent"]:
        """
        获取目标 Agent 列表
        
        Args:
            message: 消息对象
            
        Returns:
            目标 Agent 列表
        """
        logger.debug(f"[ChatHandler] 开始解析目标 Agent，消息ID: {message.id}")
        logger.debug(f"[ChatHandler] 元数据: {message.metadata}")
        
        if not self._registry:
            logger.debug(f"[ChatHandler] 无注册中心，返回默认 Agent: {self._agent_id}")
            return [self._agent]
        
        if message.metadata.get("broadcast"):
            all_agents = self._registry.list_agents()
            logger.debug(f"[ChatHandler] 广播模式，目标 Agent: {all_agents}")
            return [
                self._registry.get_agent(aid) 
                for aid in all_agents
            ]
        
        target_agents = message.metadata.get("target_agents")
        if target_agents:
            valid_agents = [aid for aid in target_agents if aid in self._registry.list_agents()]
            logger.debug(f"[ChatHandler] 多播模式，请求: {target_agents}, 有效: {valid_agents}")
            return [
                self._registry.get_agent(aid) 
                for aid in valid_agents
            ]
        
        target_id = message.metadata.get("target_agent")
        if target_id:
            logger.debug(f"[ChatHandler] 单播模式，目标 Agent: {target_id}")
            try:
                return [self._registry.get_agent(target_id)]
            except ValueError as e:
                logger.warning(f"[ChatHandler] 目标 Agent '{target_id}' 不存在，回退到默认: {self._agent_id}")
                return [self._agent]
        
        logger.debug(f"[ChatHandler] 默认模式，返回默认 Agent: {self._agent_id}")
        return [self._agent]
    
    async def handle(self, message: Message) -> MessageResponse:
        """
        处理消息，支持多 Agent 并行处理
        
        Args:
            message: 消息对象
            
        Returns:
            响应对象
        """
        handle_start = time.time()
        logger.info(f"[ChatHandler] 📨 开始处理消息 | ID: {message.id}")
        logger.debug(f"[ChatHandler] 消息内容: {message.content[:100]}..." if len(message.content) > 100 else f"[ChatHandler] 消息内容: {message.content}")
        
        agents = self._get_target_agents(message)
        agent_ids = [a.agent_id for a in agents]
        logger.debug(f"[ChatHandler] 🎯 目标 Agent: {agent_ids}")
        
        if len(agents) == 1:
            logger.debug(f"[ChatHandler] 单 Agent 处理模式")
            response = await self._handle_single(agents[0], message)
        else:
            logger.debug(f"[ChatHandler] 多 Agent 并行处理模式")
            response = await self._handle_multiple(agents, message)
        
        handle_elapsed = time.time() - handle_start
        logger.info(f"[ChatHandler] ✅ 处理完成 | 耗时: {handle_elapsed:.3f}s | 成功: {response.success}")
        
        return response
    
    async def _handle_single(
        self, 
        agent: "Agent", 
        message: Message
    ) -> MessageResponse:
        """
        处理单个 Agent
        
        Args:
            agent: Agent 实例
            message: 消息对象
            
        Returns:
            响应对象
        """
        single_start = time.time()
        logger.debug(f"[ChatHandler] 开始调用 Agent: {agent.agent_id}")
        
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: agent.chat(message.content, images=message.images)
            )
            
            single_elapsed = time.time() - single_start
            logger.info(f"[ChatHandler] 🤖 Agent '{agent.agent_id}' 执行成功 | 耗时: {single_elapsed:.3f}s")
            logger.debug(f"[ChatHandler] 响应内容长度: {len(result.get('content', ''))}")
            logger.debug(f"[ChatHandler] Token 统计 - 输入: {result.get('total_prompt_tokens', 0)}, 输出: {result.get('total_completion_tokens', 0)}")
            
            return MessageResponse(
                message_id=message.id,
                content=result.get("content", ""),
                success=True,
                metadata={
                    "agent_id": agent.agent_id,
                    "elapsed_time": result.get("elapsed_time"),
                    "total_prompt_tokens": result.get("total_prompt_tokens", 0),
                    "total_completion_tokens": result.get("total_completion_tokens", 0),
                    "total_tokens": result.get("total_tokens"),
                    "context_window": result.get("context_window", 128000),
                    "context_usage_percent": result.get("context_usage_percent", 0)
                }
            )
        except Exception as e:
            single_elapsed = time.time() - single_start
            logger.error(f"[ChatHandler] Agent '{agent.agent_id}' 执行异常，耗时: {single_elapsed:.3f}s，错误: {e}")
            return MessageResponse(
                message_id=message.id,
                success=False,
                error=str(e),
                metadata={"agent_id": agent.agent_id}
            )
    
    async def _handle_multiple(
        self, 
        agents: List["Agent"], 
        message: Message
    ) -> MessageResponse:
        """
        并行处理多个 Agent
        
        Args:
            agents: Agent 实例列表
            message: 消息对象
            
        Returns:
            聚合响应对象
        """
        multi_start = time.time()
        logger.debug(f"[ChatHandler] 开始并行处理 {len(agents)} 个 Agent")
        
        tasks = [self._handle_single(agent, message) for agent in agents]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        results = []
        for agent, resp in zip(agents, responses):
            if isinstance(resp, Exception):
                logger.debug(f"[ChatHandler] Agent '{agent.agent_id}' 返回异常: {resp}")
                results.append({
                    "agent_id": agent.agent_id, 
                    "success": False,
                    "error": str(resp)
                })
            elif isinstance(resp, MessageResponse):
                logger.debug(f"[ChatHandler] Agent '{agent.agent_id}' 返回成功: {resp.success}")
                results.append({
                    "agent_id": agent.agent_id, 
                    "success": resp.success,
                    "content": resp.content,
                    "error": resp.error
                })
            else:
                logger.warning(f"[ChatHandler] Agent '{agent.agent_id}' 返回无效类型: {type(resp)}")
                results.append({
                    "agent_id": agent.agent_id,
                    "success": False,
                    "error": f"Invalid response type: {type(resp)}"
                })
        
        success_count = sum(1 for r in results if r.get("success"))
        multi_elapsed = time.time() - multi_start
        
        logger.debug(f"[ChatHandler] 并行处理完成，成功: {success_count}/{len(agents)}，总耗时: {multi_elapsed:.3f}s")
        
        content_parts = []
        for r in results:
            if r.get("content"):
                content_parts.append(f"[{r['agent_id']}]\n{r['content']}")
            elif r.get("error"):
                content_parts.append(f"[{r['agent_id']}]\n错误: {r['error']}")
        
        return MessageResponse(
            message_id=message.id,
            content="\n---\n".join(content_parts) if content_parts else "",
            success=success_count > 0,
            metadata={"agents": results},
            responses=results
        )
    
    async def handle_stream(self, message: Message) -> StreamResponse:
        """
        流式处理消息
        
        Args:
            message: 消息对象
            
        Returns:
            流式响应包装对象，包含生成器
        """
        handle_start = time.time()
        logger.info(f"[ChatHandler] 📨 开始流式处理消息 | ID: {message.id}")
        logger.debug(f"[ChatHandler] 消息内容: {message.content[:100]}..." if len(message.content) > 100 else f"[ChatHandler] 消息内容: {message.content}")
        
        agents = self._get_target_agents(message)
        
        if len(agents) > 1:
            logger.warning(f"[ChatHandler] 流式模式不支持多 Agent，仅使用第一个: {agents[0].agent_id}")
        
        agent = agents[0]
        logger.debug(f"[ChatHandler] 🎯 目标 Agent: {agent.agent_id}")
        
        try:
            async def stream_generator():
                """流式生成器，包装 Agent 的 chat_stream"""
                chunk_count = 0
                try:
                    async for chunk in agent.chat_stream(message.content):
                        chunk_count += 1
                        yield chunk
                except Exception as e:
                    logger.error(f"[ChatHandler] 流式生成异常: {e}")
                    yield f"[错误: {e}]"
                finally:
                    elapsed = time.time() - handle_start
                    logger.info(f"[ChatHandler] ✅ 流式处理完成 | 耗时: {elapsed:.3f}s | chunks: {chunk_count}")
            
            return StreamResponse(
                message_id=message.id,
                generator=stream_generator(),
                success=True,
                metadata={
                    "agent_id": agent.agent_id,
                    "stream": True
                }
            )
        except Exception as e:
            elapsed = time.time() - handle_start
            logger.error(f"[ChatHandler] 流式处理初始化失败 | 耗时: {elapsed:.3f}s | 错误: {e}")
            return StreamResponse.error_response(message.id, str(e))


class CommandHandler:
    """
    命令处理器
    
    功能说明:
        - 处理命令类型消息
        - 支持系统命令解析和执行
        - 返回命令执行结果
    
    核心方法:
        - handle: 处理命令消息
    """
    
    def __init__(self, agent: "Agent"):
        """
        初始化命令处理器
        
        Args:
            agent: Agent 实例
        """
        self._agent = agent
        logger.debug(f"[CommandHandler] 初始化命令处理器，Agent ID: {agent.agent_id}")
    
    async def handle(self, message: Message) -> MessageResponse:
        """
        处理命令消息
        
        Args:
            message: 消息对象
            
        Returns:
            响应对象
        """
        command = message.content.strip()
        logger.debug(f"[CommandHandler] 收到命令: {command}")
        
        if command.startswith("/"):
            return await self._handle_system_command(message, command)
        
        logger.debug(f"[CommandHandler] 非系统命令，返回错误")
        return MessageResponse(
            message_id=message.id,
            success=False,
            error=f"Unknown command: {command}"
        )
    
    async def _handle_system_command(
        self, 
        message: Message, 
        command: str
    ) -> MessageResponse:
        """
        处理系统命令
        
        Args:
            message: 消息对象
            command: 命令字符串
            
        Returns:
            响应对象
        """
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        logger.debug(f"[CommandHandler] 解析命令: cmd={cmd}, args={args}")
        
        if cmd in ("/reload",):
            logger.debug(f"[CommandHandler] 执行重载命令")
            self._agent.reload()
            return MessageResponse(
                message_id=message.id,
                content="配置已重载",
                success=True
            )
        
        if cmd in ("/clear",):
            logger.debug(f"[CommandHandler] 执行清空对话命令")
            self._agent.conversation.clear()
            return MessageResponse(
                message_id=message.id,
                content="对话上下文已清空",
                success=True
            )
        
        if cmd in ("/models",):
            logger.debug(f"[CommandHandler] 执行列出模型命令")
            models = self._agent.llm_client.list_models()
            lines = ["已配置模型列表:"]
            for alias, info in models.items():
                current = " ✓ 当前" if info["is_current"] else ""
                lines.append(f"  • {alias} - {info['litellm_model']}{current}")
            return MessageResponse(
                message_id=message.id,
                content="\n".join(lines),
                success=True
            )
        
        if cmd in ("/switch",) and args:
            logger.debug(f"[CommandHandler] 执行切换模型命令，目标: {args}")
            result = self._agent.llm_client.switch_model(args)
            return MessageResponse(
                message_id=message.id,
                content=result.get("message", "模型切换完成"),
                success=result.get("success", True)
            )
        
        logger.debug(f"[CommandHandler] 未知命令: {cmd}")
        return MessageResponse(
            message_id=message.id,
            success=False,
            error=f"Unknown command: {cmd}"
        )



# 示例：定时任务处理器

# class TimerHandler:
#     """
#     定时任务处理器
    
#     功能说明:
#         - 处理定时任务触发消息
#         - 支持指定目标 Agent
#         - 支持多播任务
    
#     核心方法:
#         - handle: 处理定时任务消息
#     """
    
#     def __init__(self, registry: Optional["AgentRegistry"] = None):
#         """
#         初始化定时任务处理器
        
#         Args:
#             registry: Agent 注册中心
#         """
#         self._registry = registry
#         logger.debug(f"[TimerHandler] 初始化定时任务处理器，有注册中心: {registry is not None}")
    
#     async def handle(self, message: Message) -> MessageResponse:
#         """
#         处理定时任务消息
        
#         Args:
#             message: 消息对象
            
#         Returns:
#             响应对象
#         """
#         timer_start = time.time()
#         logger.debug(f"[TimerHandler] ========== 开始处理定时任务 ==========")
#         logger.debug(f"[TimerHandler] 消息ID: {message.id}")
#         logger.debug(f"[TimerHandler] 任务内容: {message.content[:100]}..." if len(message.content) > 100 else f"[TimerHandler] 任务内容: {message.content}")
        
#         if not self._registry:
#             logger.error(f"[TimerHandler] 无注册中心配置")
#             return MessageResponse(
#                 message_id=message.id,
#                 success=False,
#                 error="No registry configured"
#             )
        
#         target_agents = message.metadata.get("target_agents", [])
#         if not target_agents:
#             target_id = message.metadata.get("target_agent", "default")
#             target_agents = [target_id]
        
#         logger.debug(f"[TimerHandler] 目标 Agent: {target_agents}")
        
#         results = []
#         for agent_id in target_agents:
#             agent_start = time.time()
#             logger.debug(f"[TimerHandler] 开始处理 Agent: {agent_id}")
            
#             try:
#                 agent = self._registry.get_agent(agent_id)
#                 loop = asyncio.get_event_loop()
#                 result = await loop.run_in_executor(
#                     None,
#                     agent.chat,
#                     message.content
#                 )
                
#                 agent_elapsed = time.time() - agent_start
#                 logger.debug(f"[TimerHandler] Agent '{agent_id}' 执行成功，耗时: {agent_elapsed:.3f}s")
                
#                 results.append({
#                     "agent_id": agent_id,
#                     "success": True,
#                     "content": result.get("content", "")
#                 })
#             except Exception as e:
#                 agent_elapsed = time.time() - agent_start
#                 logger.error(f"[TimerHandler] Agent '{agent_id}' 执行异常，耗时: {agent_elapsed:.3f}s，错误: {e}")
#                 results.append({
#                     "agent_id": agent_id,
#                     "success": False,
#                     "error": str(e)
#                 })
        
#         success_count = sum(1 for r in results if r.get("success"))
#         timer_elapsed = time.time() - timer_start
        
#         logger.debug(f"[TimerHandler] 定时任务处理完成，成功: {success_count}/{len(target_agents)}，总耗时: {timer_elapsed:.3f}s")
#         logger.debug(f"[TimerHandler] ========== 处理定时任务结束 ==========")
        
#         return MessageResponse(
#             message_id=message.id,
#             content="\n---\n".join(
#                 f"[{r['agent_id']}]\n{r.get('content', r.get('error'))}"
#                 for r in results
#             ),
#             success=success_count > 0,
#             responses=results
#         )


