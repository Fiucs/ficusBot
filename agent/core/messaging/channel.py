#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :channel.py
# @Time      :2026/03/07
# @Author    :Ficus

"""
消息通道模块

该模块实现消息通道，支持发布/订阅模式、过滤器订阅、同步和异步发布。
"""
import asyncio
import concurrent.futures
import time
from typing import Callable, Awaitable, Dict, List, Optional, Any, TYPE_CHECKING
from loguru import logger

from agent.core.messaging.message import Message, MessageResponse

if TYPE_CHECKING:
    pass


class MessageChannel:
    """
    消息通道
    
    功能说明:
        - 支持发布/订阅模式
        - 支持过滤器订阅
        - 支持同步和异步发布
        - 支持等待响应
        - 支持多处理器并行处理
    
    核心方法:
        - subscribe: 订阅消息
        - unsubscribe: 取消订阅
        - publish: 异步发布消息
        - publish_sync: 同步发布消息
    
    使用示例:
        channel = MessageChannel()
        
        # 订阅消息
        async def handler(msg: Message) -> MessageResponse:
            return MessageResponse(message_id=msg.id, content="响应")
        
        channel.subscribe(handler, name="agent_1")
        
        # 发布消息
        response = await channel.publish(message, wait_for_response=True)
    """
    
    def __init__(self):
        """初始化消息通道"""
        self._subscribers: Dict[str, List[Dict]] = {}
        self._response_events: Dict[str, asyncio.Event] = {}
        self._responses: Dict[str, MessageResponse] = {}
        self._lock = asyncio.Lock()
        self._stats: Dict[str, int] = {
            "published": 0,
            "handled": 0,
            "errors": 0
        }
        logger.debug(f"[MessageChannel] 消息通道初始化完成")
    
    def subscribe(
        self,
        handler: Callable[[Message], Awaitable[MessageResponse]],
        name: str,
        filter_func: Optional[Callable[[Message], bool]] = None
    ) -> None:
        """
        订阅消息
        
        Args:
            handler: 消息处理函数，接收 Message，返回 MessageResponse
            name: 订阅者名称（用于取消订阅和日志）
            filter_func: 过滤函数，返回 True 表示处理该消息，None 表示处理所有消息
        """
        if name not in self._subscribers:
            self._subscribers[name] = []
        
        self._subscribers[name].append({
            "handler": handler,
            "filter": filter_func
        })
        
        has_filter = filter_func is not None
        logger.debug(f"[MessageChannel] 订阅者注册: {name}, 有过滤器: {has_filter}, 当前订阅者总数: {len(self._subscribers)}")
        
        all_names = list(self._subscribers.keys())
        logger.debug(f"[MessageChannel] 当前所有订阅者: {all_names}")
    
    def unsubscribe(self, name: str) -> bool:
        """
        取消订阅
        
        Args:
            name: 订阅者名称
            
        Returns:
            是否成功取消
        """
        if name in self._subscribers:
            del self._subscribers[name]
            logger.debug(f"[MessageChannel] 订阅者取消: {name}, 剩余订阅者: {len(self._subscribers)}")
            return True
        logger.debug(f"[MessageChannel] 取消订阅失败，未找到订阅者: {name}")
        return False
    
    def list_subscribers(self) -> List[str]:
        """
        列出所有订阅者
        
        Returns:
            订阅者名称列表
        """
        return list(self._subscribers.keys())
    
    async def publish(
        self,
        message: Message,
        wait_for_response: bool = True,
        timeout: float = 60.0
    ) -> Optional[MessageResponse]:
        """
        异步发布消息
        
        Args:
            message: 消息对象
            wait_for_response: 是否等待响应
            timeout: 超时时间（秒）
            
        Returns:
            响应对象，如果 wait_for_response=False 则返回 None
        """
        self._stats["published"] += 1
        start_time = time.time()
        
        logger.debug(f"[MessageChannel] ========== 发布消息开始 ==========")
        logger.debug(f"[MessageChannel] 消息ID: {message.id}")
        logger.debug(f"[MessageChannel] 消息来源: {message.source.value}")
        logger.debug(f"[MessageChannel] 消息类型: {message.type.value}")
        logger.debug(f"[MessageChannel] 消息内容: {message.content[:100]}..." if len(message.content) > 100 else f"[MessageChannel] 消息内容: {message.content}")
        logger.debug(f"[MessageChannel] 用户ID: {message.user_id}")
        logger.debug(f"[MessageChannel] 会话ID: {message.session_id}")
        logger.debug(f"[MessageChannel] 元数据: {message.metadata}")
        logger.debug(f"[MessageChannel] 等待响应: {wait_for_response}, 超时: {timeout}s")
        logger.debug(f"[MessageChannel] 当前订阅者数量: {len(self._subscribers)}")
        
        matched_handlers = self._find_matched_handlers(message)
        
        logger.debug(f"[MessageChannel] 匹配到的处理器数量: {len(matched_handlers)}")
        if matched_handlers:
            handler_names = [name for name, _ in matched_handlers]
            logger.debug(f"[MessageChannel] 匹配的处理器: {handler_names}")
        
        if not matched_handlers:
            logger.warning(f"[MessageChannel] 无订阅者处理消息: {message.id}")
            logger.debug(f"[MessageChannel] ========== 发布消息结束（无处理器） ==========")
            return None
        
        if not wait_for_response:
            logger.debug(f"[MessageChannel] 异步处理模式，不等待响应")
            asyncio.create_task(self._handle_all(matched_handlers, message, timeout))
            return None
        
        response = None
        if len(matched_handlers) == 1:
            name, handler = matched_handlers[0]
            logger.debug(f"[MessageChannel] 单处理器模式，处理器: {name}")
            response = await self._handle_single(name, handler, message, timeout)
        else:
            logger.debug(f"[MessageChannel] 多处理器并行模式，处理器数量: {len(matched_handlers)}")
            response = await self._handle_multiple(matched_handlers, message, timeout)
        
        elapsed = time.time() - start_time
        logger.debug(f"[MessageChannel] 消息处理完成，总耗时: {elapsed:.3f}s")
        logger.debug(f"[MessageChannel] 响应成功: {response.success if response else 'None'}")
        if response and response.error:
            logger.debug(f"[MessageChannel] 响应错误: {response.error}")
        logger.debug(f"[MessageChannel] ========== 发布消息结束 ==========")
        
        return response
    
    def _find_matched_handlers(self, message: Message) -> List[tuple]:
        """
        查找匹配的处理器
        
        Args:
            message: 消息对象
            
        Returns:
            匹配的处理器列表 [(name, handler), ...]
        """
        matched = []
        logger.debug(f"[MessageChannel] 开始匹配处理器，订阅者列表: {list(self._subscribers.keys())}")
        
        for name, subscribers in self._subscribers.items():
            for sub in subscribers:
                filter_func = sub.get("filter")
                if filter_func is None:
                    logger.debug(f"[MessageChannel] 订阅者 '{name}' 无过滤器，直接匹配")
                    matched.append((name, sub["handler"]))
                else:
                    try:
                        result = filter_func(message)
                        logger.debug(f"[MessageChannel] 订阅者 '{name}' 过滤器结果: {result}")
                        if result:
                            matched.append((name, sub["handler"]))
                    except Exception as e:
                        logger.warning(f"[MessageChannel] 订阅者 '{name}' 过滤器执行异常: {e}")
        
        return matched
    
    async def _handle_single(
        self,
        name: str,
        handler: Callable,
        message: Message,
        timeout: float
    ) -> MessageResponse:
        """
        处理单个处理器
        
        Args:
            name: 处理器名称
            handler: 处理函数
            message: 消息对象
            timeout: 超时时间
            
        Returns:
            响应对象
        """
        handler_start = time.time()
        logger.debug(f"[MessageChannel] 开始调用处理器: {name}")
        
        try:
            response = await asyncio.wait_for(
                handler(message),
                timeout=timeout
            )
            self._stats["handled"] += 1
            handler_elapsed = time.time() - handler_start
            logger.debug(f"[MessageChannel] 处理器 '{name}' 执行成功，耗时: {handler_elapsed:.3f}s")
            return response
        except asyncio.TimeoutError:
            self._stats["errors"] += 1
            handler_elapsed = time.time() - handler_start
            logger.error(f"[MessageChannel] 处理器 '{name}' 超时，耗时: {handler_elapsed:.3f}s，超时设置: {timeout}s")
            return MessageResponse(
                message_id=message.id,
                success=False,
                error=f"Handler {name} timeout after {timeout}s"
            )
        except Exception as e:
            self._stats["errors"] += 1
            handler_elapsed = time.time() - handler_start
            logger.error(f"[MessageChannel] 处理器 '{name}' 异常，耗时: {handler_elapsed:.3f}s，错误: {e}")
            return MessageResponse(
                message_id=message.id,
                success=False,
                error=f"Handler {name} error: {str(e)}"
            )
    
    async def _handle_multiple(
        self,
        handlers: List[tuple],
        message: Message,
        timeout: float
    ) -> MessageResponse:
        """
        并行处理多个处理器
        
        Args:
            handlers: 处理器列表 [(name, handler), ...]
            message: 消息对象
            timeout: 超时时间
            
        Returns:
            聚合响应对象
        """
        multi_start = time.time()
        logger.debug(f"[MessageChannel] 开始并行处理 {len(handlers)} 个处理器")
        
        tasks = [
            self._handle_single(name, handler, message, timeout)
            for name, handler in handlers
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        responses = []
        for (name, _), result in zip(handlers, results):
            if isinstance(result, Exception):
                logger.debug(f"[MessageChannel] 处理器 '{name}' 返回异常: {result}")
                responses.append({
                    "handler": name,
                    "success": False,
                    "error": str(result)
                })
            elif isinstance(result, MessageResponse):
                logger.debug(f"[MessageChannel] 处理器 '{name}' 返回成功: {result.success}")
                responses.append({
                    "handler": name,
                    "success": result.success,
                    "content": result.content[:100] + "..." if len(result.content) > 100 else result.content,
                    "error": result.error
                })
            else:
                logger.warning(f"[MessageChannel] 处理器 '{name}' 返回无效类型: {type(result)}")
                responses.append({
                    "handler": name,
                    "success": False,
                    "error": f"Invalid response type: {type(result)}"
                })
        
        success_count = sum(1 for r in responses if r.get("success"))
        multi_elapsed = time.time() - multi_start
        
        logger.debug(f"[MessageChannel] 并行处理完成，成功: {success_count}/{len(handlers)}，总耗时: {multi_elapsed:.3f}s")
        
        content_parts = []
        for r in responses:
            if r.get("content"):
                content_parts.append(f"[{r['handler']}]\n{r['content']}")
            elif r.get("error"):
                content_parts.append(f"[{r['handler']}]\n错误: {r['error']}")
        
        return MessageResponse(
            message_id=message.id,
            content="\n---\n".join(content_parts) if content_parts else "",
            success=success_count > 0,
            metadata={"handler_count": len(handlers), "success_count": success_count},
            responses=responses
        )
    
    async def _handle_all(
        self,
        handlers: List[tuple],
        message: Message,
        timeout: float
    ) -> None:
        """
        异步处理所有处理器（不等待响应）
        
        Args:
            handlers: 处理器列表
            message: 消息对象
            timeout: 超时时间
        """
        logger.debug(f"[MessageChannel] 异步处理模式，开始处理 {len(handlers)} 个处理器")
        try:
            await self._handle_multiple(handlers, message, timeout)
            logger.debug(f"[MessageChannel] 异步处理完成")
        except Exception as e:
            logger.error(f"[MessageChannel] 异步处理异常: {e}")
    
    def publish_sync(
        self,
        message: Message,
        timeout: float = 60.0
    ) -> Optional[MessageResponse]:
        """
        同步发布消息（非异步环境使用）
        
        Args:
            message: 消息对象
            timeout: 超时时间（秒）
            
        Returns:
            响应对象
        """
        logger.debug(f"[MessageChannel] 同步发布消息: {message.id}")
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                logger.debug(f"[MessageChannel] 事件循环正在运行，使用线程池执行")
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        self._run_sync_in_thread,
                        message,
                        timeout
                    )
                    result = future.result(timeout=timeout + 5)
                    logger.debug(f"[MessageChannel] 同步发布完成（线程池模式）")
                    return result
            else:
                logger.debug(f"[MessageChannel] 使用现有事件循环执行")
                result = loop.run_until_complete(
                    self.publish(message, wait_for_response=True, timeout=timeout)
                )
                logger.debug(f"[MessageChannel] 同步发布完成（事件循环模式）")
                return result
        except RuntimeError:
            logger.debug(f"[MessageChannel] 创建新事件循环执行")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.publish(message, wait_for_response=True, timeout=timeout)
                )
                logger.debug(f"[MessageChannel] 同步发布完成（新事件循环模式）")
                return result
            finally:
                loop.close()
    
    def _run_sync_in_thread(
        self,
        message: Message,
        timeout: float
    ) -> Optional[MessageResponse]:
        """
        在独立线程中运行同步发布
        
        Args:
            message: 消息对象
            timeout: 超时时间
            
        Returns:
            响应对象
        """
        logger.debug(f"[MessageChannel] 在独立线程中执行同步发布")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.publish(message, wait_for_response=True, timeout=timeout)
            )
        finally:
            loop.close()
    
    @property
    def stats(self) -> Dict[str, int]:
        """获取统计信息"""
        stats = self._stats.copy()
        logger.debug(f"[MessageChannel] 当前统计: {stats}")
        return stats
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        logger.debug(f"[MessageChannel] 重置统计信息，原统计: {self._stats}")
        self._stats = {
            "published": 0,
            "handled": 0,
            "errors": 0
        }
