# FicusBot 项目架构文档

> 本文档记录了 FicusBot 项目的整体结构、技术栈和核心模块，便于后续开发参考。

---

## 一、项目概述

FicusBot 是一个功能完善的智能助手框架，采用模块化设计，支持多模型、多平台、多 Agent 架构。

### 核心特性

- **多 LLM 支持**：通过 LiteLLM 统一接口，支持 OpenAI、通义、Ollama 等多种模型
- **多 Agent 架构**：单进程内运行多个 Agent 实例，懒加载模式
- **消息层架构**：统一消息入口，支持单播/多播/广播路由模式
- **技能系统**：基于 Markdown 定义，动态加载和注入
- **MCP 协议**：支持 Model Context Protocol，扩展工具能力
- **多平台 Bot**：支持 7 个主流平台（Telegram、飞书、Discord、QQ、企业微信、钉钉、Slack）

---

## 二、目录结构

```
ficusbot/
├── run.py                    # Agent 启动入口（CLI/API 模式）
├── run_bot.py                # Bot 网关启动入口（多平台机器人）
├── requirements.txt          # 项目依赖
├── config.json               # 配置文件（运行时生成）
│
├── agent/                    # 核心模块
│   ├── main.py               # Agent 入口函数（run_cli, get_agent, start_agents, get_app）
│   ├── registry.py           # Agent 注册中心（多Agent架构）
│   │
│   ├── config/               # 配置模块
│   │   ├── configloader.py   # 全局配置加载器
│   │   └── agent_config.py   # Agent 配置数据类
│   │
│   ├── core/                 # 核心组件
│   │   ├── agent.py          # Agent 核心类
│   │   ├── conversation.py   # 对话上下文管理器
│   │   └── messaging/        # 消息层模块（新增）
│   │       ├── __init__.py   # 模块导出
│   │       ├── message.py    # 统一消息格式
│   │       ├── channel.py    # 消息通道
│   │       ├── handlers.py   # 消息处理器
│   │       ├── application.py # 应用程序单例
│   │       └── middlewares.py # 中间件
│   │
│   ├── provider/             # LLM 提供者
│   │   └── llmclient.py      # LiteLLM 客户端封装
│   │
│   ├── memory/               # 记忆系统模块（新增）
│   │   ├── __init__.py
│   │   └── memory_system.py  # 统一记忆系统类
│   │
│   ├── fileSystem/           # 文件操作工具
│   │   ├── filesystem.py     # 文件系统工具实现
│   │   └── path_resolver.py  # 路径解析器
│   │
│   ├── skill/                # 技能系统
│   │   └── skill_loader.py   # 技能加载器
│   │
│   ├── tool/                 # 工具模块
│   │   ├── tooladapter.py    # 工具适配器（统一接口）
│   │   ├── shelltool.py      # Shell 命令工具
│   │   ├── browsertool.py    # 浏览器自动化工具
│   │   ├── subagent_tool.py  # 子代理委托工具
│   │   └── tools.json        # 工具配置定义
│   │
│   ├── mcp/                  # MCP 协议模块
│   │   ├── mcp_manager.py    # MCP 管理器
│   │   ├── mcp_client.py     # MCP 客户端
│   │   ├── mcp_config.py     # MCP 配置
│   │   └── mcp_tool_adapter.py # MCP 工具适配器
│   │
│   ├── storage/              # 存储模块
│   │   ├── base_storage.py   # 存储基类
│   │   ├── session_storage.py # 会话存储
│   │   └── tinydb_storage.py # TinyDB 实现
│   │
│   ├── server/               # 统一服务模块
│   │   ├── gateway.py        # 统一网关
│   │   ├── bot/              # Bot 子模块
│   │   │   ├── base_listener.py  # 监听器基类
│   │   │   ├── message_bus.py    # 消息总线
│   │   │   ├── core_processor.py # 核心处理器
│   │   │   └── listeners/        # 平台监听器
│   │   │       ├── telegram.py
│   │   │       ├── lark.py (飞书)
│   │   │       ├── discord.py
│   │   │       ├── qq.py
│   │   │       ├── wecom.py (企业微信)
│   │   │       ├── dingtalk.py
│   │   │       └── slack.py
│   │   ├── command/          # 命令处理模块
│   │   ├── interceptor/      # 拦截器系统
│   │   └── http/             # HTTP API 模块
│   │       ├── app.py        # FastAPI 应用
│   │       ├── http_result.py # 统一响应格式
│   │       └── routes/       # API 路由
│   │
│   └── utils/                # 工具类
│       ├── logger.py         # 日志配置
│       ├── network.py        # 网络工具
│       └── command_utils.py  # 命令工具
│
├── workspace/                # 工作区
│   ├── agents.md             # 系统提示词配置
│   ├── skills/               # 技能目录
│   │   ├── skill-creator/    # 技能创建工具
│   │   ├── test-workflow-skill/ # 测试工作流技能
│   │   ├── exa-web-search-free/ # Exa 搜索技能
│   │   └── find-skills/      # 技能查找
│   ├── memory/               # 记忆系统目录（新增）
│   │   ├── memory_index/     # 索引文件目录
│   │   │   ├── tool_index.json    # 工具索引（JSON5格式）
│   │   │   └── memory_index.json  # 记忆索引（JSON5格式）
│   │   └── vector_db/        # LanceDB 向量数据库
│   │       ├── memories/     # 记忆表
│   │       └── tools/        # 工具表
│   ├── models/               # 本地模型目录（新增）
│   │   └── huggingface/      # HuggingFace/GGUF 模型
│   └── README.MD
│
├── sessions/                 # 会话数据目录
│   └── chat_session_map.json
│
└── test/                     # 测试文件目录
```

---

## 三、技术栈

### 核心依赖

| 类别 | 依赖 | 版本 | 用途 |
|------|------|------|------|
| **LLM 框架** | litellm | 1.81.10 | 多模型统一接口（OpenAI/通义/Ollama等） |
| **Web 框架** | fastapi | 0.129.0 | HTTP API 服务 |
| **Web 服务器** | uvicorn | 0.40.0 | ASGI 服务器 |
| **数据验证** | pydantic | 2.12.5 | 数据模型验证 |
| **配置解析** | pyyaml | 6.0.3 | YAML 配置文件 |
| **Frontmatter** | python-frontmatter | 1.1.0 | SKILL.md 元数据解析 |
| **JSON Schema** | jsonschema | 4.26.0 | 工具参数校验 |
| **JSON5** | pyjson5 | 2.0.0 | 支持注释的 JSON 解析 |
| **终端 UI** | textual | 3.2.0 | TUI 终端界面 |
| **终端颜色** | colorama | 0.4.6 | 终端彩色输出 |
| **日志** | loguru | - | 结构化日志 |
| **数据库** | tinydb | - | 轻量级 JSON 数据库 |
| **向量数据库** | lancedb | - | 嵌入式向量数据库（新增） |
| **嵌入模型** | sentence-transformers | - | HuggingFace 嵌入模型（新增） |
| **GGUF 支持** | llama-cpp-python | - | GGUF 量化模型加载（新增） |
| **数据结构** | pyarrow | - | LanceDB Schema 定义（新增） |

### 可选依赖

| 类别 | 依赖 | 用途 |
|------|------|------|
| **MCP 协议** | mcp >= 1.0.0 | Model Context Protocol 支持 |
| **浏览器自动化** | browser-use, playwright | 网页操作能力 |
| **Telegram Bot** | python-telegram-bot >= 21.0 | Telegram 机器人 |
| **WebSocket** | websockets >= 12.0 | 实时通信 |
| **飞书** | lark-oapi | 飞书机器人 |
| **Discord** | discord.py | Discord 机器人 |
| **企业微信** | wechatpy | 企业微信机器人 |
| **Slack** | slack-bolt | Slack 机器人 |

---

## 四、核心模块详解

### 4.1 Agent 核心 (agent/core/agent.py)

Agent 类是系统的核心，负责：
- 对话处理和上下文管理
- 工具调用和结果处理
- 与 LLM 的交互

**关键方法**：
- `chat()`: 处理用户消息
- `execute_tool()`: 执行工具调用
- `_build_messages()`: 构建消息上下文

### 4.2 Agent 入口函数 (agent/main.py)

提供 Agent 的入口函数，便于外部调用：

| 函数 | 说明 |
|------|------|
| `run_cli(agent)` | 命令行交互界面 |
| `get_agent(agent_id)` | 获取指定 Agent 实例（延迟加载） |
| `start_agents(agent_ids)` | 批量启动 Agent 实例 |
| `get_app()` | 获取 FastAPI 应用实例 |

### 4.3 Agent 注册中心 (agent/registry.py)

管理多个 Agent 实例：
- 懒加载模式，按需创建
- 支持不同配置的 Agent
- 子代理委托机制

### 4.4 LLM 客户端 (agent/provider/llmclient.py)

LiteLLM 封装：
- 统一的多模型接口
- 支持流式输出
- 错误处理和重试

### 4.5 对话管理 (agent/core/conversation.py)

对话上下文管理：
- 历史消息存储
- 上下文窗口管理
- 会话持久化

### 4.6 技能系统 (agent/skill/skill_loader.py)

技能加载和管理：
- 扫描 `workspace/skills/` 目录
- 解析 SKILL.md 的 YAML frontmatter
- 动态注册为 Function Calling 工具

**技能定义格式**：
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
```

### 4.7 工具适配器 (agent/tool/tooladapter.py)

统一的工具调用接口：

```
ToolAdapter
├── 文件工具
│   ├── file_read
│   ├── file_write
│   ├── file_delete
│   └── file_search ...
├── Shell 工具
│   ├── shell_exec
│   └── shell_safe_exec
├── 技能工具 (skill_xxx)
│   └── 动态加载自 SKILL.md
├── MCP 工具
│   └── mcp.{server}.{tool}
├── 浏览器工具
│   └── browser_navigate, browser_click ...
└── 子代理工具 (agent_xxx_delegate)
    └── 多 Agent 委托
```

**工具和技能过滤机制**：

Agent 配置中的 `tools` 和 `skills` 字段支持过滤：

| 字段 | 过滤方法 | 说明 |
|------|---------|------|
| `tools` | `_filter_tools()` | 过滤非技能工具，支持通配符 `*` |
| `skills` | `_filter_skills()` | 过滤技能工具，支持通配符 `*` |

过滤实现位置：
- `agent/core/agent.py` - `_filter_tools()` 和 `_filter_skills()` 方法
- `agent/skill/skill_loader.py` - `get_skill_list_info(patterns)` 方法

### 4.8 MCP 管理器 (agent/mcp/mcp_manager.py)

MCP 协议支持：
- 连接本地和远程 MCP Server
- 自动发现和注册工具
- 与现有工具系统集成

### 4.9 存储模块 (agent/storage/)

数据持久化：
- `BaseStorage`: 存储基类，定义统一接口
- `TinyDBStorage`: TinyDB 实现
- `SessionStorage`: 会话存储

**BaseStorage 接口**：
```python
class BaseStorage(ABC):
    def save(self, key, data)      # 保存数据
    def load(self, key)            # 加载数据
    def delete(self, key)          # 删除数据
    def exists(self, key)          # 检查存在
    def list_all()                 # 列出所有键
    def clear()                    # 清空数据
```

### 4.10 Bot 网关 (agent/server/gateway.py)

统一网关：
- Bot + HTTP API 统一入口
- 消息路由和处理
- 命令系统支持

### 4.11 消息层 (agent/core/messaging/)

消息层提供统一的消息处理架构，支持多 Agent 路由。

**核心组件**：

| 组件 | 文件 | 功能 |
|------|------|------|
| 消息格式 | `message.py` | 统一消息格式、枚举定义、响应格式 |
| 消息通道 | `channel.py` | 发布/订阅模式、过滤器订阅、同步/异步发布 |
| 消息处理器 | `handlers.py` | 单播/多播/广播路由、Agent 并行处理 |
| 应用程序 | `application.py` | 单例模式、全局通道管理 |
| 中间件 | `middlewares.py` | 日志、验证、限流等中间件 |

**路由模式**：

| 模式 | metadata 配置 | 说明 |
|------|--------------|------|
| 单播 | `{"target_agent": "coder"}` | 发送到指定 Agent |
| 多播 | `{"target_agents": ["coder", "assistant"]}` | 发送到多个 Agent |
| 广播 | `{"broadcast": True}` | 发送到所有 Agent |
| 默认 | 无配置 | 发送到默认 Agent |

**使用示例**：

```python
from agent.core.messaging import (
    Message, MessageSource, MessageType, get_channel
)

# 发送消息到指定 Agent
response = await get_channel().publish(
    Message.create(
        source=MessageSource.API,
        type=MessageType.CHAT,
        content="分析这段代码",
        metadata={"target_agent": "coder"}
    ),
    wait_for_response=True
)
```

**初始化流程**：

```python
# agent/main.py
def _init_messaging(agent_ids: Optional[List[str]] = None):
    """初始化消息层"""
    from agent.core.messaging import Application, ChatHandler
    from agent.registry import AGENT_REGISTRY
    
    app = Application.with_registry(AGENT_REGISTRY)
    channel = app.initialize()
    
    if agent_ids is None:
        agent_ids = ["default"]
    
    loaded_agents = AGENT_REGISTRY.preload_agents(agent_ids)
    
    for agent_id, agent in loaded_agents.items():
        handler = ChatHandler(agent_id, agent, AGENT_REGISTRY)
        channel.subscribe(
            handler.handle,
            name=agent_id,
            filter_func=lambda msg, aid=agent_id: (
                msg.metadata.get("target_agent") == aid or
                msg.metadata.get("target_agent") is None
            )
        )
    
    return app
```

---

## 五、启动方式

### 入口文件

| 文件 | 用途 | 启动模式 |
|------|------|----------|
| run.py | Agent 启动器 | CLI / API |
| run_bot.py | Bot 网关启动器 | Bot + CLI + API |

### 启动命令

```bash
# Agent 模式
python run.py                      # CLI 模式（默认）
python run.py --api                # API 服务模式
python run.py --all-agents         # 启动所有 Agent + CLI
python run.py --api --all-agents   # 启动所有 Agent + API

# Bot 网关模式
python run_bot.py                  # Bot 服务
python run_bot.py --cli            # Bot + CLI
python run_bot.py --api            # Bot + API
python run_bot.py --all-agents     # Bot + 所有 Agent
```

---

## 六、工具配置 (tools.json)

工具配置使用 JSON5 格式（支持注释）：

```json
{
  "name": "tool_name",
  "description": "工具描述",
  "parameters": {
    "type": "object",
    "properties": {
      "param1": {
        "type": "string",
        "description": "参数说明"
      }
    },
    "required": ["param1"]
  },
  "method": "method_name"  // 绑定到 ToolAdapter 的方法
}
```

---

## 七、配置文件结构

### config.json

```json
{
  "llm": {
    "model": "gpt-4o-mini",
    "api_key": "${OPENAI_API_KEY}",
    "base_url": null
  },
  "agent": {
    "name": "default",
    "system_prompt": "..."
  },
  "mcp": {
    "servers": [...]
  },
  "storage": {
    "type": "tinydb",
    "path": "./sessions"
  }
}
```

### workspace/agents.md

系统提示词配置，使用 Markdown 格式。

---

## 八、平台支持

| 平台 | 实现文件 | 依赖 |
|------|----------|------|
| Telegram | listeners/telegram.py | python-telegram-bot |
| 飞书 | listeners/lark.py | lark-oapi |
| Discord | listeners/discord.py | discord.py |
| QQ | listeners/qq.py | - |
| 企业微信 | listeners/wecom.py | wechatpy |
| 钉钉 | listeners/dingtalk.py | - |
| Slack | listeners/slack.py | slack-bolt |

---

## 九、安全控制

### 文件操作白名单

在 `filesystem.py` 中配置允许访问的目录。

### Shell 命令控制

在 `shelltool.py` 中配置：
- 命令白名单
- 命令黑名单
- 危险命令拦截

### 路径访问控制

`path_resolver.py` 负责路径验证和安全检查。

---

## 十、待开发功能

- [x] 多 Agent 架构
- [x] 技能系统
- [x] MCP 协议支持
- [x] 多平台 Bot 网关
- [x] 长记忆对话，工具使用（已完成）
- [ ] 视觉化操作 Agent
- [ ] Web UI 界面

---

## 十一、开发规范

参考 `.trae/rules/project_rules.md`：

1. 代码变更需更新 README.MD、DOCS.MD、plan.MD
2. 代码需添加标准 docstring 注释（类/方法/参数/返回值）
3. 测试文件放 test 目录，保留不删除
4. API 响应统一使用 `HttpResult` 类，格式：`{success, message, data}`
5. 命名：类用 PascalCase，函数用 snake_case，常量用 UPPER_CASE
6. 日志用 loguru，异常需明确信息
7. 基类文件必须以 `base` 开头

---

## 十二、关键文件路径

| 功能 | 文件路径 |
|------|----------|
| Agent 核心 | agent/core/agent.py |
| Agent 入口函数 | agent/main.py |
| 消息层模块 | agent/core/messaging/ |
| 消息格式 | agent/core/messaging/message.py |
| 消息通道 | agent/core/messaging/channel.py |
| 消息处理器 | agent/core/messaging/handlers.py |
| 工具适配器 | agent/tool/tooladapter.py |
| 技能加载器 | agent/skill/skill_loader.py |
| MCP 管理器 | agent/mcp/mcp_manager.py |
| 存储基类 | agent/storage/base_storage.py |
| 统一网关 | agent/server/gateway.py |
| 工具配置 | agent/tool/tools.json |
| 系统提示词 | workspace/agents.md |
| 技能目录 | workspace/skills/ |
| 记忆系统 | agent/memory/memory_system.py |
| 工具索引 | workspace/memory/memory_index/tool_index.json |
| 记忆索引 | workspace/memory/memory_index/memory_index.json |
| 向量数据库 | workspace/memory/vector_db/ |
| 本地模型 | workspace/models/ |

---

*文档生成时间: 2026-03-07*
