# 🌳 FicusBot

<p align="center">
  <strong>🤖 智能多平台 AI 助手</strong>
</p>

<p align="center">
  <em>多模型 • 多Agent • 多平台 • MCP协议 • 技能扩展</em>
</p>

<p align="center">
  基于 LiteLLM 构建，支持 QQ/Telegram/飞书/Discord/钉钉/Slack 等多平台
</p>

<p align="center">
  <a href="#功能特性">功能特性</a> •
  <a href="#快速开始">快速开始</a> •
  <a href="#使用指南">使用指南</a> •
  <a href="#配置说明">配置说明</a> •
  <a href="#开发文档">开发文档</a>
</p>

---

## 功能特性

- 🤖 **多模型支持** - OpenAI、阿里云通义千问、Ollama 本地模型
- 🎭 **多Agent架构** - 支持多Agent实例和子代理委托，每个Agent可配置不同模型、工具、技能
- 📁 **文件操作** - 安全的文件系统工具（读、写、删、搜索等）
- 💻 **Shell 执行** - 受保护的 Shell 命令执行
- 🛠️ **技能系统** - 自定义 Skill 扩展，Markdown 格式定义
- 🔌 **MCP 协议** - 支持 Model Context Protocol，扩展工具能力
- 🌐 **浏览器自动化** - 基于 browser-use 的浏览器操作能力，支持 Token 优化配置
- 🤖 **多平台机器人** - 支持 QQ、Telegram、飞书、Discord、企业微信、钉钉、Slack
- 💾 **会话持久化** - 自动保存对话历史，支持多会话管理
- 📊 **上下文使用率** - 实时显示 token 消耗和上下文使用率
- 📝 **日志系统** - 文件日志、控制台彩色输出、日志过滤
- 🔒 **安全控制** - 文件/Shell 白名单、黑名单保护

## 快速开始

### 安装依赖

```bash
pip install pyyaml python-frontmatter jsonschema pyjson5 litellm fastapi uvicorn colorama loguru tinydb

# MCP 协议支持（可选）
pip install mcp

# 浏览器自动化支持（可选）
pip install browser-use playwright
playwright install chromium

# Bot 网关依赖（可选）
pip install python-telegram-bot lark-oapi discord.py aiohttp
```

### 运行

```bash
# === run.py (Agent 启动器) ===
python run.py                      # CLI 模式（默认）
python run.py --api                # API 服务模式
python run.py --all-agents         # 启动所有 Agent + CLI
python run.py --api --all-agents   # 启动所有 Agent + API
python run.py --agents default coder  # 启动指定 Agent
python run.py --api --port 8080    # 指定端口

# === run_bot.py (Bot 网关启动器) ===
python run_bot.py                  # Bot 服务
python run_bot.py --cli            # Bot + CLI
python run_bot.py --api            # Bot + API
python run_bot.py --cli --api      # Bot + CLI + API
python run_bot.py --all-agents     # Bot + 所有 Agent
python run_bot.py --all-agents --api  # Bot + 所有 Agent + API
python run_bot.py --echo           # 回声测试模式
```

### 启动模式说明

**run.py (Agent 启动器)**


| 命令                               | 模式 | Agent   |
| ---------------------------------- | ---- | ------- |
| `python run.py`                    | CLI  | default |
| `python run.py --api`              | API  | default |
| `python run.py --all-agents`       | CLI  | 所有    |
| `python run.py --api --all-agents` | API  | 所有    |

**run_bot.py (Bot 网关启动器)**


| 命令                                   | Bot | CLI | API | Agent   |
| -------------------------------------- | --- | --- | --- | ------- |
| `python run_bot.py`                    | ✅  | ❌  | ❌  | default |
| `python run_bot.py --cli`              | ✅  | ✅  | ❌  | default |
| `python run_bot.py --api`              | ✅  | ❌  | ✅  | default |
| `python run_bot.py --cli --api`        | ✅  | ✅  | ✅  | default |
| `python run_bot.py --all-agents`       | ✅  | ❌  | ❌  | 所有    |
| `python run_bot.py --all-agents --api` | ✅  | ❌  | ✅  | 所有    |

### Bot 多平台配置

> **模块路径变更**: `agent/bot/` 已重命名为 `agent/server/`，支持 Bot 网关 + HTTP API + 拦截器系统。详见 [GATEWAY_DESIGN.md](./GATEWAY_DESIGN.md)

#### 1. 飞书 (Feishu)

```json
{
  "bot": {
    "channels": {
      "feishu": {
        "enabled": true,
        "appId": "cli_xxxxxxxxxxxxxxxx",
        "appSecret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "mode": "websocket",
        "domain": "feishu",
        "groupPolicy": "open"
      }
    }
  }
}
```

**获取凭证**：

1. 访问 [飞书开放平台](https://open.feishu.cn/)
2. 创建企业自建应用
3. 在「凭证与基础信息」中获取 App ID 和 App Secret
4. 在「权限管理」中添加 `im:chat:readonly` 和 `im:message:send_as_bot` 权限
5. 在「事件订阅」中订阅 `im.message.receive_v1` 事件
6. 发布应用并安装到企业

**连接模式**：

- `websocket` - WebSocket 长连接（推荐，无需公网地址）
- `webhook` - HTTP Webhook（需要公网地址）

---

#### 2. Telegram

```json
{
  "bot": {
    "channels": {
      "telegram": {
        "enabled": true,
        "token": "1234567890:ABCdefGHIjklMNOpqrSTUvwxyz",
        "proxy": "socks5://127.0.0.1:1080"
      }
    }
  }
}
```

**获取 Token**：

1. 在 Telegram 中搜索 `@BotFather`
2. 发送 `/newbot` 创建新机器人
3. 按提示设置名称和用户名
4. 获得 Token（格式：`数字:字母数字混合`）

**代理配置**（可选）：

- 中国大陆访问需要代理
- 支持 `socks5` 和 `http` 代理

---

#### 3. QQ

```json
{
  "bot": {
    "channels": {
      "qq": {
        "enabled": true,
        "ws_url": "ws://localhost:3001",
        "access_token": "your_token"
      }
    }
  }
}
```

**架构说明**：

```
FicusBot <--WebSocket--> go-cqhttp <--QQ协议--> QQ服务器
```

**部署 go-cqhttp**：

1. 下载 [go-cqhttp](https://github.com/Mrs4s/go-cqhttp/releases)
2. 编辑 `config.yml`：

```yaml
servers:
  - ws:
      host: 0.0.0.0
      port: 3001
```

3. 启动并扫码登录
4. 配置 FicusBot 连接到 `ws://localhost:3001`

⚠️ **风险提示**：使用第三方 QQ 框架存在封号风险，建议使用小号测试

---

#### 4. Discord

```json
{
  "bot": {
    "channels": {
      "discord": {
        "enabled": true,
        "token": "YOUR_DISCORD_BOT_TOKEN_HERE"
      }
    }
  }
}
```

**获取 Token**：

1. 访问 [Discord Developer Portal](https://discord.com/developers/applications)
2. 创建 New Application
3. 进入 Bot 页面，点击「Add Bot」
4. 在 Bot 页面点击「Reset Token」获取 Token
5. 开启 `MESSAGE CONTENT INTENT` 权限

**邀请机器人**：

1. 进入 OAuth2 > URL Generator
2. 选择 `bot` 和 `applications.commands`
3. 选择权限：`Send Messages`, `Read Message History`
4. 使用生成的链接邀请机器人到服务器

---

#### 5. 企业微信 (WeCom)

```json
{
  "bot": {
    "channels": {
      "wecom": {
        "enabled": true,
        "corp_id": "wwxxxxxxxxxxxxxxxx",
        "agent_id": "1000002",
        "secret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "token": "your_token",
        "encoding_aes_key": "your_aes_key"
      }
    }
  }
}
```

**获取凭证**：

1. 访问 [企业微信管理后台](https://work.weixin.qq.com/)
2. 进入「应用管理」-「自建应用」-「创建应用」
3. 获取 `AgentId` 和 `Secret`
4. Corp ID 在「我的企业」页面获取

**接收消息**（可选）：

- 如需主动接收消息而非轮询，需配置 Token 和 EncodingAESKey
- 在应用详情页「接收消息」中设置

---

#### 6. 钉钉 (DingTalk)

```json
{
  "bot": {
    "channels": {
      "dingtalk": {
        "enabled": true,
        "app_key": "dingxxxxxxxxxxxxxxxx",
        "app_secret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "robot_code": "your_robot_code"
      }
    }
  }
}
```

**获取凭证**：

1. 访问 [钉钉开放平台](https://open.dingtalk.com/)
2. 创建企业内部应用
3. 在「应用信息」中获取 App Key 和 App Secret
4. 在「机器人」页面获取 Robot Code

**权限配置**：

- 添加 `机器人应用` 权限
- 添加 `企业内机器人发送消息` 权限

---

#### 7. Slack

```json
{
  "bot": {
    "channels": {
      "slack": {
        "enabled": true,
        "bot_token": "xoxb-YOUR-BOT-TOKEN-HERE",
        "app_token": "xapp-YOUR-APP-TOKEN-HERE",
        "signing_secret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

**获取凭证**：

1. 访问 [Slack API](https://api.slack.com/apps)
2. 点击「Create New App」-「From scratch」
3. 进入「OAuth & Permissions」：
   - 添加 `chat:write`, `im:read`, `mpim:read` 等权限
   - 点击「Install to Workspace」获取 Bot Token
4. 进入「Basic Information」-「App-Level Tokens」：
   - 点击「Generate Token and Scopes」
   - 添加 `connections:write` 权限
   - 获取 App Token
5. 在「Basic Information」中获取 Signing Secret

**启用 Socket Mode**：

1. 进入「Socket Mode」页面
2. 开启 Socket Mode
3. 确保 App Token 有 `connections:write` 权限

---

### Bot 依赖安装

```bash
# 飞书
pip install lark-oapi

# Telegram
pip install python-telegram-bot

# QQ (需要 go-cqhttp 作为中间服务)
pip install websockets

# Discord
pip install discord.py

# 企业微信
pip install wechatpy

# 钉钉
pip install websockets

# Slack
pip install slack-bolt

# 安装所有 Bot 依赖
pip install lark-oapi python-telegram-bot discord.py websockets wechatpy slack-bolt

# 混合模式（CLI + Bot 同时运行）
python run_bot.py --cli

# 或使用模块方式
python -m agent.main --cli
```

首次运行会自动生成 `config.json` 配置文件。

## 使用指南

### 系统提示词配置

系统提示词存放在 `workspace/agents.md` 文件中，可以随时修改：

- 修改后使用 `/reload` 重载生效
- 支持模板变量：`{workspace_root}`, `{INJECTED_SKILLS_LIST}`, `{INJECTED_SKILLS}`
- 如果文件不存在，使用内置默认提示词

### 技能系统

技能目录结构：

```
workspace/skills/
└── skill_name/
    ├── SKILL.md        # 技能定义（必需）
    ├── scripts/        # 脚本资源（可选）
    └── references/     # 参考文档（可选）
```

内置技能：

- `skill-creator` - 技能创建工具
- `test-workflow-skill` - 测试工作流技能

**技能列表注入**：

系统启动时，会自动将所有可用技能注入到 system prompt 中，格式如下：

```
# 当前可用技能
## 技能列表

- name: exa-web-search-free
  description: Free AI search via Exa MCP...
- name: skill-creator
  description: Guide for creating effective skills...
```

大模型在第一轮对话即可知道有哪些可用技能。

## 配置说明

### 多Agent架构

FicusBot 支持多 Agent 架构，允许配置多个专用 Agent 实例，每个 Agent 可以使用不同的模型、工具和技能。

#### 架构说明

```
┌─────────────────────────────────────────────────────────────┐
│                      单进程架构                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  AgentRegistry                       │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐            │   │
│  │  │ default  │ │  coder   │ │researcher│  ...       │   │
│  │  │ (配置)   │ │ (配置)   │ │ (配置)   │            │   │
│  │  └────┬─────┘ └──────────┘ └──────────┘            │   │
│  │       │                                             │   │
│  │       ▼ 懒加载                                      │   │
│  │  ┌──────────┐                                       │   │
│  │  │  Agent   │ ← 启动时只创建 default               │   │
│  │  │  实例    │   其他Agent按需创建                   │   │
│  │  └──────────┘                                       │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**关键点：**

- 所有Agent运行在**同一进程内**，非多进程
- 启动时只创建 default Agent 实例
- 其他Agent采用**懒加载**模式，首次访问时才创建
- Agent之间通过**子代理委托**机制协作

#### 使用场景


| 场景            | 说明                             | 配置方式                                                   |
| --------------- | -------------------------------- | ---------------------------------------------------------- |
| **单Agent模式** | 只使用默认Agent处理所有任务      | `sub_agent_config.enabled: false`                          |
| **子代理委托**  | 主Agent自动委托任务给专用子Agent | `sub_agent_config.enabled: true` + `sub_agents: ["coder"]` |
| **手动切换**    | 代码中主动获取特定Agent          | `AGENT_REGISTRY.get_agent("coder")`                        |
| **API多端点**   | 不同API端点使用不同Agent         | 路由到不同Agent实例                                        |

#### 场景一：单Agent模式（推荐入门）

适合大多数场景，配置简单：

```json
{
  "agents": {
    "default": {
      "model": "zai/glm-4.6v",
      "tools": ["*"],
      "skills": ["*"],
      "sub_agents": []
    }
  },
  "sub_agent_config": {
    "enabled": false
  }
}
```

#### 场景二：子代理委托模式

主Agent自动将专业任务委托给子Agent：

```json
{
  "agents": {
    "default": {
      "model": "zai/glm-4.6v",
      "tools": ["*"],
      "sub_agents": ["coder", "researcher"]
    },
    "coder": {
      "model": "deepseek/deepseek-coder",
      "tools": ["file_*", "shell_*"],
      "system_prompt": "你是代码专家..."
    },
    "researcher": {
      "model": "zai/glm-4.6v",
      "tools": ["browser_*", "mcp_*"],
      "system_prompt": "你是研究助手..."
    }
  },
  "sub_agent_config": {
    "enabled": true,
    "max_delegation_depth": 3
  }
}
```

**工作流程：**

```
用户: "帮我写一个爬虫，并搜索最新的爬虫最佳实践"

default Agent 会：
1. 调用 agent_coder_delegate → 创建 coder Agent 编写代码
2. 调用 agent_researcher_delegate → 创建 researcher Agent 搜索信息
3. 整合结果返回给用户
```

#### 场景三：手动切换Agent

在代码中主动获取特定Agent：

```python
from agent.registry import AGENT_REGISTRY

# 获取代码专家处理代码任务
coder = AGENT_REGISTRY.get_agent("coder")
coder.chat("帮我重构这段代码")

# 获取研究助手搜索信息
researcher = AGENT_REGISTRY.get_agent("researcher")
researcher.chat("搜索最新的AI论文")
```

#### 场景四：API多端点服务

为不同类型任务提供专用API端点：

```python
from fastapi import FastAPI
from agent.registry import AGENT_REGISTRY

app = FastAPI()

@app.post("/chat/code")
async def code_chat(request: ChatRequest):
    """代码专用端点"""
    agent = AGENT_REGISTRY.get_agent("coder")
    return agent.chat(request.message)

@app.post("/chat/research")
async def research_chat(request: ChatRequest):
    """研究专用端点"""
    agent = AGENT_REGISTRY.get_agent("researcher")
    return agent.chat(request.message)

@app.post("/chat")
async def default_chat(request: ChatRequest):
    """通用端点"""
    agent = AGENT_REGISTRY.get_agent("default")
    return agent.chat(request.message)
```

#### 配置示例

```json
{
  "agents": {
    "default": {
      "description": "默认通用Agent，处理一般性任务",
      "model": "zai/glm-4.6v",
      "tools": ["*"],
      "skills": ["*"],
      "sub_agents": ["coder", "researcher"],
      "max_tool_calls": 8
    },
    "coder": {
      "description": "代码专家Agent，专注于代码编写、审查、调试",
      "model": "deepseek/deepseek-coder",
      "llm_preset": "coder",
      "tools": ["file_*", "shell_*"],
      "skills": ["skill-creator"],
      "system_prompt": "你是一个专业的代码专家，擅长编写高质量代码、代码审查和调试。",
      "max_tool_calls": 10
    },
    "researcher": {
      "description": "研究Agent，专注于信息搜索和分析",
      "model": "zai/glm-4.6v",
      "llm_preset": "researcher",
      "tools": ["browser_*", "mcp_*"],
      "skills": ["exa-web-search-free"],
      "system_prompt": "你是一个专业的研究助手，擅长信息搜索、分析和总结。"
    }
  },
  "llm": {
    "agent_presets": {
      "coder": {
        "temperature": 0.5,
        "max_tokens": 16000,
        "timeout": 120
      },
      "researcher": {
        "temperature": 0.2,
        "max_tokens": 12000
      }
    }
  },
  "sub_agent_config": {
    "enabled": true,
    "max_delegation_depth": 3,
    "timeout": 120
  }
}
```

#### 动态注册Agent

```python
from agent.registry import AGENT_REGISTRY
from agent.config.agent_config import AgentConfig

config = AgentConfig(
    agent_id="temp_analyst",
    description="临时数据分析 Agent",
    model="openai/gpt4o",
    tools=["file_*", "shell_*"]
)
AGENT_REGISTRY.register_agent(config)
```

### 主要配置项

```json
{
  "workspace_root": "./workspace",
  "file_allow_list": ["./workspace"],
  "llm": {
    "global": {
      "temperature": 0.3,
      "max_tokens": 8096,
      "context_window": 128000,
      "timeout": 60,
      "drop_params": true
    },
    "default_model": "openai/gpt35",
    "providers": {
      "openai": {
        "api_key": "your-key",
        "models": {
          "gpt35": {
            "model_name": "gpt-3.5-turbo",
            "remark": "OpenAI GPT-3.5"
          }
        }
      },
      "zai": {
        "api_key": "your-key",
        "api_base": "https://open.bigmodel.cn/api/paas/v4",
        "models": {
          "glm-4.6v": {
            "remark": "智谱 GLM-4.6V",
            "stream": true,
            "thinking": {
              "type": "enabled"
            }
          }
        }
      }
    }
  },
  "session": {
    "enable_persistence": true,
    "storage_dir": "./sessions",
    "max_sessions": 100,
    "expire_days": 30
  },
  "log": {
    "enable_file": true,
    "log_dir": "./logs",
    "level": "INFO"
  }
}
```

### 模型参数配置

模型参数支持**四层配置**，优先级从高到低：

| 层级 | 配置位置 | 说明 |
|------|---------|------|
| 1. 预设级别 | `llm.agent_presets.{preset_name}` | Agent 专用预设，最高优先级 |
| 2. 模型级别 | `llm.providers.{vendor}.models.{model}` | 针对特定模型 |
| 3. 厂商级别 | `llm.providers.{vendor}` | 针对厂商下所有模型 |
| 4. 全局级别 | `llm.global` | 默认值，所有模型继承 |

**配置合并顺序**：`global` → `provider` → `model` → `preset`，后者覆盖前者。

**支持的参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `temperature` | float | 0.3 | 控制输出随机性 (0-1)，0=确定性，1=创造性 |
| `max_tokens` | int | 8096 | 单次回复最大 token 数 |
| `context_window` | int | 128000 | 模型上下文窗口大小（输入+输出总容量） |
| `timeout` | int | 60 | API 请求超时时间（秒） |
| `stream` | bool | false | 是否启用流式输出 |
| `drop_params` | bool | true | 是否自动丢弃模型不支持的参数 |
| `thinking` | object | - | 思考模式配置（部分模型支持） |

### thinking 参数详解

`thinking` 参数用于启用模型的深度思考/推理模式，不同厂商有不同的参数格式：

| 厂商 | 参数格式 | 配置示例 |
|------|---------|---------|
| **智谱 GLM** | `extra_body.thinking` | `{"enabled": true}` |
| **DeepSeek** | `extra_body.thinking` | `{"enabled": true}` |
| **豆包/火山** | `extra_body.thinking` | `{"enabled": true}` |
| **阿里千问** | `extra_body.enable_thinking` | `true` |
| **LM Studio** | `extra_body.enable_thinking` | `true` |
| **Gemini** | `thinking_budget` | `1024` (token数) |
| **Claude** | 顶层 `thinking` | `{"type": "enabled", "budget_tokens": 1024}` |
| **OpenAI o系列** | `reasoning_effort` | `"low"` / `"medium"` / `"high"` |

**配置示例**：

```json
{
  "llm": {
    "global": {
      "temperature": 0.3,
      "max_tokens": 8096,
      "context_window": 128000,
      "timeout": 60,
      "drop_params": true
    },
    "agent_presets": {
      "coder": {
        "temperature": 0.5,
        "max_tokens": 16000,
        "timeout": 120
      },
      "researcher": {
        "temperature": 0.2,
        "max_tokens": 12000
      }
    },
    "providers": {
      "zai": {
        "api_key": "your-key",
        "api_base": "https://open.bigmodel.cn/api/paas/v4",
        "models": {
          "glm-4.6v": {
            "model_name": "glm-4.6v",
            "remark": "智谱 GLM-4.6V 深度思考模型",
            "stream": true,
            "thinking": {
              "enabled": true
            }
          },
          "glm-4.7": {
            "model_name": "glm-4.7",
            "remark": "智谱 GLM-4.7",
            "max_tokens": 16000
          }
        }
      },
      "deepseek": {
        "api_key": "your-key",
        "models": {
          "deepseek-reasoner": {
            "model_name": "deepseek-reasoner",
            "remark": "DeepSeek 深度推理模型",
            "thinking": {
              "enabled": true
            }
          }
        }
      },
      "anthropic": {
        "api_key": "your-key",
        "models": {
          "claude-3-7-sonnet": {
            "model_name": "claude-3-7-sonnet-20250219",
            "thinking": {
              "enabled": true,
              "mode": "thinking",
              "budget_tokens": 1024
            }
          }
        }
      },
      "gemini": {
        "api_key": "your-key",
        "models": {
          "gemini-2.5-pro": {
            "model_name": "gemini-2.5-pro-preview-05-06",
            "thinking": {
              "enabled": true,
              "budget_tokens": 2048
            }
          }
        }
      },
      "openai": {
        "api_key": "your-key",
        "models": {
          "o1-mini": {
            "model_name": "o1-mini",
            "thinking": {
              "mode": "reasoning_effort",
              "effort": "medium"
            }
          }
        }
      }
    }
  }
}
```

> **⚠️ LM Studio 需先在设置中开启**：「Settings → Developer → Separate reasoning_content and content in API responses」

### Agent LLM 预设参数

Agent 可以通过 `llm_preset` 引用预设参数，实现不同 Agent 使用不同的 LLM 配置：

```json
{
  "agents": {
    "coder": {
      "model": "deepseek/deepseek-coder",
      "llm_preset": "coder",
      "tools": ["file_*", "shell_*"]
    }
  },
  "llm": {
    "agent_presets": {
      "coder": {
        "temperature": 0.5,
        "max_tokens": 16000,
        "timeout": 120
      }
    }
  }
}
```

**优先级**：`llm_preset` > `模型配置` > `厂商配置` > `全局配置`

### 安全配置


| 配置项                 | 说明               |
| ---------------------- | ------------------ |
| `file_allow_list`      | 文件操作白名单目录 |
| `shell_cmd_whitelist`  | Shell 命令白名单   |
| `shell_cmd_deny_list`  | Shell 命令黑名单   |
| `shell_path_whitelist` | Shell 路径白名单   |

### 浏览器 Token 优化配置

浏览器工具支持多种 Token 优化策略，可大幅减少 LLM 调用成本：

```json
{
  "browser_state_mode": "interactive",
  "browser_max_elements": 20,
  "browser_prioritize_visible": true,
  "browser_max_text_length": 30,
  "browser_include_page_summary": true,
  "browser_summary_max_length": 300
}
```


| 配置项                         | 说明                                         | 默认值        |
| ------------------------------ | -------------------------------------------- | ------------- |
| `browser_state_mode`           | 状态提取模式：`interactive`/`minimal`/`full` | `interactive` |
| `browser_max_elements`         | 最大返回元素数量 (5-50)                      | `20`          |
| `browser_prioritize_visible`   | 只返回视口可见元素                           | `true`        |
| `browser_max_text_length`      | 单元素文本最大长度                           | `30`          |
| `browser_include_page_summary` | 是否包含页面摘要                             | `true`        |
| `browser_summary_max_length`   | 页面摘要最大长度                             | `300`         |

**模式说明**：

- `interactive`：只返回可交互元素（按钮、链接、输入框等），推荐使用，可减少 60-80% Token
- `minimal`：只返回关键元素（主要导航、主要按钮），最省 Token
- `full`：返回所有可点击元素，消耗最多 Token

## 项目结构

```
ficusbot/
├── run.py              # 启动入口
├── config.json         # 配置文件
├── agent/
│   ├── main.py         # 主程序（Agent 类）
│   ├── registry.py     # Agent 注册中心（多Agent架构）
│   ├── config/         # 配置加载
│   │   ├── configloader.py  # 配置加载器
│   │   └── agent_config.py  # Agent 配置数据类
│   ├── core/           # 核心组件
│   │   └── conversation.py  # 对话上下文管理器
│   ├── fileSystem/     # 文件操作
│   ├── skill/          # 技能系统
│   ├── tool/           # 工具模块
│   │   ├── tooladapter.py   # 工具适配器
│   │   ├── shelltool.py     # Shell 工具
│   │   ├── browsertool.py   # 浏览器工具
│   │   └── subagent_tool.py # 子代理工具
│   ├── storage/        # 会话存储
│   ├── tui/            # TUI 终端界面
│   ├── mcp/            # MCP 协议模块
│   ├── server/         # 统一服务模块
│   │   ├── gateway.py          # 统一网关
│   │   ├── bot/                # Bot 子模块
│   │   │   ├── message_bus.py      # 消息总线
│   │   │   ├── base_listener.py    # 监听器基类
│   │   │   ├── core_processor.py   # 核心处理器
│   │   │   ├── chat_session_map.py # 会话映射
│   │   │   └── listeners/          # 平台监听器
│   │   ├── command/            # 命令处理模块
│   │   │   ├── command_handler.py  # 命令处理器
│   │   │   ├── command_context.py  # 命令上下文
│   │   │   └── command_result.py   # 命令结果
│   │   ├── interceptor/        # 拦截器系统
│   │   │   ├── base.py             # 拦截器基类
│   │   │   ├── interceptor_chain.py# 拦截器链
│   │   │   └── builtins/           # 内置拦截器
│   │   └── http/              # HTTP API 模块
│   │       ├── app.py              # FastAPI 应用
│   │       ├── http_result.py      # 统一响应格式
│   │       └── routes/             # API 路由
│   └── utils/          # 工具类
├── workspace/          # 工作区
│   ├── agents.md       # 系统提示词配置文件
│   └── skills/         # 技能目录
├── sessions/           # 会话数据
│   ├── sessions.json   # 会话存储
│   └── config.json     # 会话配置
├── test/               # 测试文件
│   └── test_multi_agent.py  # 多Agent功能测试
└── logs/               # 日志文件
```

## 开发文档

详细文档请参阅 [DOCS.MD](./DOCS.MD)

- [配置中心](./DOCS.MD#1-配置中心)
- [工具系统](./DOCS.MD#2-工具系统)
- [核心 Agent](./DOCS.MD#3-核心-agent)
- [会话持久化](./DOCS.MD#8-会话持久化系统)
- [日志系统](./DOCS.MD#9-日志系统)
- [MCP 协议模块](./DOCS.MD#11-mcp-model-context-protocol-模块)
- [Bot 多平台适配器](./DOCS.MD#12-bot-多平台适配器模块)

## 已完成功能

- [ ]  ✅ 多模型支持（OpenAI、通义千问、Ollama 本地模型）
- [ ]  ✅ 多 Agent 架构（子代理委托、懒加载）
- [ ]  ✅ ReAct 提示词框架 + 系统提示词外部化
- [ ]  ✅ 会话持久化（TinyDB）+ 日志系统（loguru）
- [ ]  ✅ 文件系统工具（读、写、删、搜索等）
- [ ]  ✅ Shell 命令执行（白名单/黑名单保护）
- [ ]  ✅ 技能系统（Markdown 格式定义）
- [ ]  ✅ MCP 协议支持 + 浏览器自动化（browser-use）
- [ ]  ✅ 多平台 Bot 网关（Telegram、飞书、Discord、QQ、企业微信、钉钉、Slack）
- [ ]  ✅ Bot 命令系统（`/help`、`/new`、`/sessions`、`/clear`、`/models`、`/switch`、`/reload`）
- [ ]  ✅ HTTP API 模块（FastAPI）+ 拦截器系统（权限验证、限流、敏感词过滤）
- [ ]  ✅ 安全控制（文件/Shell/路径 白名单黑名单）
- [ ]  长记忆对话，工具使用
- [ ]  视觉化操作 Agent S3或者 [UI-TARS-desktop](https://github.com/bytedance/UI-TARS-desktop)
- [ ]  web UI 界面

详细开发计划请参阅 [plan.MD](./plan.MD)

## 最近更新

### 2026-03-04

- **模型参数配置文档更新**：完善四层配置优先级说明（预设 > 模型 > 厂商 > 全局）
- **thinking 参数详解**：新增各厂商 thinking 参数格式对照表，包括智谱GLM、DeepSeek、豆包、千问、Gemini、Claude、OpenAI o系列等
- **Agent LLM 预设参数**：新增 `llm.agent_presets` 配置说明，支持不同 Agent 使用不同的 LLM 参数

### 2026-03-03

- **统一 API 响应格式**：新增 `HttpResult` 类，所有 HTTP API 响应统一为 `{success, message, data}` 格式
- **修复 /models 命令**：返回所有配置的模型列表，并标记当前使用的模型
- **修复 /help 命令**：返回的命令列表添加 `/` 前缀
- **修复 /clear 命令**：修正方法调用错误
- **文件重命名**：`response.py` → `result.py`，`ApiResponse` → `HttpResult`，使命名风格统一

### 2026-03-02

- **工具命名规范修改**：将所有工具名称从点号分隔改为下划线分隔，兼容 DeepSeek 等模型
- **飞书 WebSocket 多进程隔离**：修复 asyncio 事件循环冲突问题
- **会话记忆同步修复**：解决 `ChatSessionMap` 和 `SessionStorage` 不同步导致的记忆丢失问题

## License

MIT
