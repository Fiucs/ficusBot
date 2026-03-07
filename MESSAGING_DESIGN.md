# FicusBot 消息层设计方案

> 本文档描述 FicusBot 消息层的架构设计和实施方案。

---

## 一、设计目标

- **统一消息入口**：所有输入源通过统一的消息通道发送消息
- **解耦输入与处理**：输入方只管发送，处理方只管处理
- **多 Agent 路由**：支持单播、多播、广播三种路由模式
- **易于扩展**：新增输入源只需实现消息发布

---

## 二、架构设计

### 2.1 目录结构

```
agent/core/messaging/          # 消息层模块
├── __init__.py               # 模块导出
├── message.py                # 统一消息格式
├── channel.py                # 消息通道（发布/订阅）
├── dispatcher.py             # 消息分发器
├── handlers.py               # 消息处理器
└── middlewares.py            # 中间件
```

### 2.2 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│  输入层: CLI / HTTP API / Bot / Timer / Plugin / External       │
└───────────────────────────┬─────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  消息层: MessageChannel → Middleware → MessageDispatcher        │
└───────────────────────────┬─────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  处理层: ChatHandler / TimerHandler / CommandHandler            │
│          ↓                                                      │
│  Agent 路由: 单播 / 多播 / 广播                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、核心组件

### 3.1 消息枚举定义

```python
from enum import Enum


class MessageSource(str, Enum):
    """消息来源枚举"""
    CLI = "cli"
    API = "api"
    BOT = "bot"
    TIMER = "timer"
    PLUGIN = "plugin"
    EXTERNAL = "external"


class MessageType(str, Enum):
    """消息类型枚举"""
    CHAT = "chat"
    COMMAND = "command"
    TASK_TRIGGER = "task_trigger"
    EVENT = "event"
```

### 3.2 消息格式

```python
from dataclasses import dataclass, field
from typing import Dict, Optional
import uuid
import time


@dataclass
class Message:
    """
    统一消息格式
    
    Attributes:
        id: 消息ID，自动生成UUID
        source: 来源枚举值
        type: 类型枚举值
        content: 消息内容
        user_id: 用户ID
        session_id: 会话ID
        metadata: 元数据（含路由信息）
        timestamp: 时间戳
    """
    id: str
    source: MessageSource
    type: MessageType
    content: str
    user_id: str = ""
    session_id: Optional[str] = None
    metadata: Dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    
    @classmethod
    def create(
        cls,
        source: MessageSource,
        type: MessageType,
        content: str,
        **kwargs
    ) -> "Message":
        """创建消息实例"""
        return cls(
            id=str(uuid.uuid4()),
            source=source,
            type=type,
            content=content,
            **kwargs
        )
```

### 3.3 消息响应

```python
@dataclass
class MessageResponse:
    """
    消息响应格式
    
    Attributes:
        message_id: 原消息ID
        content: 响应内容
        success: 是否成功
        error: 错误信息
        metadata: 元数据
        responses: 多播/广播时的子响应列表
    """
    message_id: str
    content: str = ""
    success: bool = True
    error: Optional[str] = None
    metadata: Dict = field(default_factory=dict)
    responses: Optional[List[Dict]] = None  # 多播/广播聚合响应
```

### 3.4 全局消息通道管理

```python
from typing import Optional, TYPE_CHECKING
import threading

if TYPE_CHECKING:
    from agent.registry import AgentRegistry


class Application:
    """
    应用程序 - 单例模式，全局管理消息通道
    
    功能说明:
        - 管理全局唯一的消息通道
        - 支持 AgentRegistry 注入
        - 提供统一的通道获取接口
    
    核心方法:
        - get_instance: 获取单例实例
        - with_registry: 使用注册中心创建实例
        - channel: 获取消息通道属性
    """
    
    _instance: Optional["Application"] = None
    _lock = threading.RLock()
    
    def __new__(cls) -> "Application":
        """单例模式：确保全局只有一个实例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化应用程序"""
        if self._initialized:
            return
        self._channel: Optional["MessageChannel"] = None
        self._registry: Optional["AgentRegistry"] = None
        self._initialized = True
    
    @classmethod
    def get_instance(cls) -> "Application":
        """获取单例实例"""
        return cls()
    
    @classmethod
    def with_registry(cls, registry: "AgentRegistry") -> "Application":
        """
        使用注册中心创建实例
        
        Args:
            registry: Agent 注册中心实例
            
        Returns:
            Application 实例
        """
        instance = cls()
        instance._registry = registry
        return instance
    
    def initialize(self) -> "MessageChannel":
        """
        初始化消息通道
        
        Returns:
            MessageChannel 实例
        """
        if self._channel is None:
            from agent.core.messaging.channel import MessageChannel
            self._channel = MessageChannel()
        return self._channel
    
    @property
    def channel(self) -> "MessageChannel":
        """获取消息通道"""
        if self._channel is None:
            self.initialize()
        return self._channel
    
    @property
    def registry(self) -> Optional["AgentRegistry"]:
        """获取 Agent 注册中心"""
        return self._registry


def get_channel() -> "MessageChannel":
    """全局获取通道"""
    return Application.get_instance().channel
```

**使用方式**：
```python
# CLI / HTTP API / Timer / Bot 都这样获取
from agent.core.messaging import get_channel
channel = get_channel()  # 拿到全局唯一的通道
```

### 3.5 消息通道

```python
import asyncio
from typing import Callable, Awaitable, Dict, List, Optional, Any
from loguru import logger


class MessageChannel:
    """
    消息通道
    
    功能说明:
        - 支持发布/订阅模式
        - 支持过滤器订阅
        - 支持同步和异步发布
        - 支持等待响应
    
    核心方法:
        - subscribe: 订阅消息
        - unsubscribe: 取消订阅
        - publish: 异步发布消息
        - publish_sync: 同步发布消息
    """
    
    def __init__(self):
        self._subscribers: Dict[str, List[Dict]] = {}
        self._response_events: Dict[str, asyncio.Event] = {}
        self._responses: Dict[str, MessageResponse] = {}
        self._lock = asyncio.Lock()
    
    def subscribe(
        self,
        handler: Callable[["Message"], Awaitable["MessageResponse"]],
        name: str,
        filter_func: Optional[Callable[["Message"], bool]] = None
    ) -> None:
        """
        订阅消息
        
        Args:
            handler: 消息处理函数
            name: 订阅者名称
            filter_func: 过滤函数，返回 True 表示处理该消息
        """
        if name not in self._subscribers:
            self._subscribers[name] = []
        
        self._subscribers[name].append({
            "handler": handler,
            "filter": filter_func
        })
        logger.debug(f"[MessageChannel] 订阅者注册: {name}")
    
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
            return True
        return False
    
    async def publish(
        self,
        message: "Message",
        wait_for_response: bool = False,
        timeout: float = 60.0
    ) -> Optional["MessageResponse"]:
        """
        异步发布消息
        
        Args:
            message: 消息对象
            wait_for_response: 是否等待响应
            timeout: 超时时间（秒）
            
        Returns:
            响应对象，如果 wait_for_response=False 则返回 None
        """
        logger.debug(f"[MessageChannel] 发布消息: {message.id}, 类型: {message.type}")
        
        matched_handlers = []
        for name, subscribers in self._subscribers.items():
            for sub in subscribers:
                filter_func = sub.get("filter")
                if filter_func is None or filter_func(message):
                    matched_handlers.append((name, sub["handler"]))
        
        if not matched_handlers:
            logger.warning(f"[MessageChannel] 无订阅者处理消息: {message.id}")
            return None
        
        if len(matched_handlers) == 1:
            name, handler = matched_handlers[0]
            try:
                response = await asyncio.wait_for(
                    handler(message),
                    timeout=timeout
                )
                return response
            except asyncio.TimeoutError:
                logger.error(f"[MessageChannel] 处理超时: {name}")
                return MessageResponse(
                    message_id=message.id,
                    success=False,
                    error=f"Handler {name} timeout"
                )
        else:
            tasks = [
                self._handle_with_timeout(name, handler, message, timeout)
                for name, handler in matched_handlers
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            responses = []
            for (name, _), result in zip(matched_handlers, results):
                if isinstance(result, Exception):
                    responses.append({
                        "handler": name,
                        "success": False,
                        "error": str(result)
                    })
                else:
                    responses.append({
                        "handler": name,
                        "success": result.success,
                        "content": result.content,
                        "error": result.error
                    })
            
            success_count = sum(1 for r in responses if r["success"])
            return MessageResponse(
                message_id=message.id,
                content="\n---\n".join(
                    f"[{r['handler']}]\n{r.get('content', r.get('error'))}"
                    for r in responses
                ),
                success=success_count > 0,
                responses=responses
            )
    
    async def _handle_with_timeout(
        self,
        name: str,
        handler: Callable,
        message: "Message",
        timeout: float
    ) -> "MessageResponse":
        """带超时的处理函数"""
        try:
            return await asyncio.wait_for(handler(message), timeout=timeout)
        except asyncio.TimeoutError:
            return MessageResponse(
                message_id=message.id,
                success=False,
                error=f"Handler {name} timeout"
            )
    
    def publish_sync(
        self,
        message: "Message",
        timeout: float = 60.0
    ) -> Optional["MessageResponse"]:
        """
        同步发布消息（非异步环境使用）
        
        Args:
            message: 消息对象
            timeout: 超时时间（秒）
            
        Returns:
            响应对象
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        self._run_sync_in_thread,
                        message,
                        timeout
                    )
                    return future.result(timeout=timeout + 5)
            else:
                return loop.run_until_complete(
                    self.publish(message, wait_for_response=True, timeout=timeout)
                )
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    self.publish(message, wait_for_response=True, timeout=timeout)
                )
            finally:
                loop.close()
    
    def _run_sync_in_thread(
        self,
        message: "Message",
        timeout: float
    ) -> Optional["MessageResponse"]:
        """在独立线程中运行同步发布"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.publish(message, wait_for_response=True, timeout=timeout)
            )
        finally:
            loop.close()
```

### 3.6 重要细节

**1. Agent 名称 = 路由标识**
- `config.json` 中的 `agents.coder` → 路由时 `target_agent: "coder"`
- 默认 Agent 名称为 `default`

**2. 订阅过滤器绑定（注意闭包问题）**
```python
# 为每个 Agent 创建订阅时绑定过滤器
# 注意：必须使用默认参数绑定 agent_id，避免闭包问题
for agent_id in registry.list_agents():
    handler = ChatHandler(agent_id, agent)
    channel.subscribe(
        handler.handle,
        name=agent_id,
        # 正确写法：使用默认参数绑定 agent_id
        filter_func=lambda msg, aid=agent_id: (
            msg.metadata.get("target_agent") == aid or
            msg.metadata.get("target_agent") is None
        )
    )
```

**3. 同步/异步兼容**
```python
# 异步发布（推荐）
response = await channel.publish(message, wait_for_response=True)

# 同步发布（非异步环境）
response = channel.publish_sync(message)
```

**4. 响应超时**
```python
response = await channel.publish(
    message, 
    wait_for_response=True,
    timeout=60.0  # 超时时间（秒）
)
```

---

## 四、Agent 路由模式

### 4.1 路由类型

| 模式 | metadata 配置 | 说明 |
|------|--------------|------|
| **单播** | `{"target_agent": "coder"}` | 发送到指定 Agent |
| **多播** | `{"target_agents": ["coder", "assistant"]}` | 发送到多个 Agent |
| **广播** | `{"broadcast": True}` | 发送到所有 Agent |
| **默认** | 无配置 | 发送到默认 Agent |

### 4.2 路由实现

```python
import asyncio
from typing import List, Optional, TYPE_CHECKING

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
    
    核心方法:
        - handle: 处理消息
        - _get_target_agents: 获取目标 Agent 列表
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
    
    def _get_target_agents(self, message: "Message") -> List["Agent"]:
        """
        获取目标 Agent 列表。
        
        路由优先级：
        1. broadcast=True → 所有 Agent
        2. target_agents=["a", "b"] → 指定多个 Agent
        3. target_agent="a" → 指定单个 Agent
        4. 默认 → 默认 Agent
        """
        if not self._registry:
            return [self._agent]
        
        # 广播：所有 Agent
        if message.metadata.get("broadcast"):
            return [
                self._registry.get_agent(aid) 
                for aid in self._registry.list_agents()
            ]
        
        # 多播：指定多个 Agent
        target_agents = message.metadata.get("target_agents")
        if target_agents:
            return [self._registry.get_agent(aid) for aid in target_agents]
        
        # 单播：指定单个 Agent
        target_id = message.metadata.get("target_agent")
        if target_id:
            return [self._registry.get_agent(target_id)]
        
        # 默认：默认 Agent
        return [self._agent]
    
    async def handle(self, message: "Message") -> "MessageResponse":
        """处理消息，支持多 Agent 并行处理"""
        agents = self._get_target_agents(message)
        
        if len(agents) == 1:
            # 单 Agent：返回单个响应
            return await self._handle_single(agents[0], message)
        else:
            # 多 Agent：并行处理，返回聚合响应
            return await self._handle_multiple(agents, message)
    
    async def _handle_single(
        self, 
        agent: "Agent", 
        message: "Message"
    ) -> "MessageResponse":
        """处理单个 Agent"""
        try:
            # Agent.chat 是同步方法，需要在异步环境中运行
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                agent.chat,
                message.content
            )
            return MessageResponse(
                message_id=message.id,
                content=result.get("content", ""),
                success=True,
                metadata={
                    "agent_id": agent.agent_id,
                    "elapsed_time": result.get("elapsed_time"),
                    "total_tokens": result.get("total_tokens")
                }
            )
        except Exception as e:
            return MessageResponse(
                message_id=message.id,
                success=False,
                error=str(e)
            )
    
    async def _handle_multiple(
        self, 
        agents: List["Agent"], 
        message: "Message"
    ) -> "MessageResponse":
        """并行处理多个 Agent"""
        tasks = [self._handle_single(agent, message) for agent in agents]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 聚合响应
        results = []
        for agent, resp in zip(agents, responses):
            if isinstance(resp, Exception):
                results.append({
                    "agent_id": agent.agent_id, 
                    "success": False,
                    "error": str(resp)
                })
            else:
                results.append({
                    "agent_id": agent.agent_id, 
                    "success": resp.success,
                    "content": resp.content,
                    "error": resp.error
                })
        
        success_count = sum(1 for r in results if r.get("success"))
        
        return MessageResponse(
            message_id=message.id,
            content="\n---\n".join(
                f"[{r['agent_id']}]\n{r.get('content', r.get('error'))}" 
                for r in results
            ),
            success=success_count > 0,
            metadata={"agents": results},
            responses=results
        )
```

---

## 五、使用示例

### 5.1 单播（发送到指定 Agent）

```python
from agent.core.messaging import Message, MessageSource, MessageType, get_channel

response = await get_channel().publish(
    Message.create(
        source=MessageSource.CLI,
        type=MessageType.CHAT,
        content="写一个 Python 脚本",
        metadata={"target_agent": "coder"}
    ),
    wait_for_response=True
)
```

### 5.2 多播（发送到多个 Agent）

```python
response = await get_channel().publish(
    Message.create(
        source=MessageSource.API,
        type=MessageType.CHAT,
        content="分析这段代码的安全性和性能",
        metadata={"target_agents": ["coder", "security", "performance"]}
    ),
    wait_for_response=True
)
# 返回聚合响应，包含每个 Agent 的结果
```

### 5.3 广播（发送到所有 Agent）

```python
response = await get_channel().publish(
    Message.create(
        source=MessageSource.TIMER,
        type=MessageType.TASK_TRIGGER,
        content="系统状态检查",
        metadata={"broadcast": True}
    ),
    wait_for_response=True
)
# 所有 Agent 都会处理并返回结果
```

### 5.4 定时任务指定 Agent

```python
task = TimerTask(
    id="daily_review",
    content="每日代码审查",
    interval=86400,
    target_agents=["coder", "security"]  # 多播
)
```

---

## 六、Agent 配置

### 6.1 单 Agent 配置

```json
{
    "agents": {
        "default": {
            "description": "默认通用Agent",
            "model": "openai/gpt4o",
            "tools": ["*"],
            "skills": ["*"]
        }
    }
}
```

### 6.2 多 Agent 配置

```json
{
    "agents": {
        "default": {
            "description": "默认通用Agent",
            "model": "openai/gpt4o",
            "tools": ["*"],
            "sub_agents": ["coder", "assistant"]
        },
        "coder": {
            "description": "代码专家",
            "model": "openai/gpt4o",
            "tools": ["file_*", "shell_*"]
        },
        "assistant": {
            "description": "助理",
            "model": "openai/gpt35",
            "tools": ["file_*"]
        }
    }
}
```

---

## 七、启动方式

### 7.1 单 Agent

```python
from agent.core.messaging import Application
from agent.main import get_agent

agent = get_agent("default")
app = Application.get_instance()
channel = app.initialize()

# 注册处理器
from agent.core.messaging.handlers import ChatHandler
handler = ChatHandler("default", agent)
channel.subscribe(handler.handle, name="default")

await app.initialize()
```

### 7.2 多 Agent

```python
from agent.core.messaging import Application
from agent.registry import AGENT_REGISTRY
from agent.core.messaging.handlers import ChatHandler

# 启动所有 Agent
AGENT_REGISTRY.start_all_agents()

# 创建应用并注册处理器
app = Application.with_registry(AGENT_REGISTRY)
channel = app.initialize()

for agent_id in AGENT_REGISTRY.list_agents():
    agent = AGENT_REGISTRY.get_agent(agent_id)
    handler = ChatHandler(agent_id, agent, AGENT_REGISTRY)
    channel.subscribe(
        handler.handle,
        name=agent_id,
        filter_func=lambda msg, aid=agent_id: (
            msg.metadata.get("target_agent") == aid or
            msg.metadata.get("target_agent") is None
        )
    )
```

---

## 八、与现有 MessageBus 的关系

### 8.1 架构对比

| 组件 | 用途 | 特点 |
|------|------|------|
| **MessageChannel** | 统一消息层 | 基于消息内容的发布/订阅，支持路由 |
| **MessageBus** | Bot 事件总线 | 基于事件类型的发布/订阅，用于监听器通信 |

### 8.2 兼容适配

```python
# 现有 MessageBus 作为 MessageChannel 的适配层
class MessageBusAdapter:
    """MessageBus 到 MessageChannel 的适配器"""
    
    def __init__(self, channel: MessageChannel):
        self._channel = channel
    
    async def on_unified_message(self, data: dict):
        """处理来自 MessageBus 的消息"""
        message = Message.create(
            source=MessageSource.BOT,
            type=MessageType.CHAT,
            content=data.get("content", ""),
            user_id=data.get("user_id", ""),
            session_id=data.get("chat_id"),
            metadata={
                "platform": data.get("platform"),
                "listener": data.get("listener")
            }
        )
        response = await self._channel.publish(message, wait_for_response=True)
        return response
```

---

## 九、改动清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `agent/core/messaging/__init__.py` | 模块导出 |
| `agent/core/messaging/message.py` | 消息格式、枚举定义 |
| `agent/core/messaging/channel.py` | 消息通道 |
| `agent/core/messaging/dispatcher.py` | 消息分发器 |
| `agent/core/messaging/handlers.py` | 消息处理器（含路由） |
| `agent/core/messaging/middlewares.py` | 中间件 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `agent/main.py` | CLI 使用消息通道 |
| `agent/server/http/routes/chat.py` | API 使用消息通道 |
| `agent/server/bot/message_bus.py` | 兼容层适配 |

---

## 十、路由模式对比

| 模式 | 配置 | 响应 | 适用场景 |
|------|------|------|----------|
| 单播 | `target_agent` | 单个响应 | 指定专家处理 |
| 多播 | `target_agents` | 聚合响应 | 多角度分析 |
| 广播 | `broadcast: true` | 聚合响应 | 系统通知、状态检查 |
| 默认 | 无 | 单个响应 | 普通对话 |

---

*文档版本: 1.3*
*更新时间: 2026-03-07*
