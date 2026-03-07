# FicusBot 记忆系统与插件集成设计

> 版本：1.0  
> 日期：2026-03-07  
> 状态：待评审

---

## 一、记忆系统架构概述

### 1.1 现有记忆系统架构

FicusBot 已有完善的记忆系统，支持工具的动态加载：

```
tool_index.json 配置:
├── enabled: false → 工具被禁用
├── add_to_memory: true → 存入向量DB，按需加载
└── add_to_memory: false → 常驻内存

工作流程:
1. Agent 初始化时，MemorySystem 处理所有工具
2. 根据 tool_index.json 配置分类工具
3. add_to_memory=true 的工具从内存移除，存入向量DB
4. 运行时通过 search_memory 搜索并动态注册
```

---

## 二、记忆索引文件职责分工

记忆系统使用两个 JSON 文件进行管理，职责明确分离：

### 2.1 文件职责对比

| 文件 | 路径 | 职责 | 存储内容 |
|------|------|------|---------|
| `memory_index.json` | `workspace/memory/memory_index/` | 存储用户记忆 | 对话记录、事实、偏好、任务结果 |
| `tool_index.json` | `workspace/memory/memory_index/` | 管理工具配置 | 工具开关、记忆功能启停、查询计数 |

### 2.2 memory_index.json 结构

```json
{
  "version": "1.0",
  "updated_at": "2026-03-07 12:00:00",
  "memories": [
    {
      "id": "f80e6557",
      "content": "Vue 3 + Tailwind CSS 框架推荐...",
      "memory_type": "fact",
      "importance": 5,
      "tags": ["Vue3", "TailwindCSS"],
      "created_at": "2026-03-06 20:53:23"
    }
  ]
}
```

**字段说明**：
- `id`: 记忆唯一标识（8位UUID）
- `content`: 记忆内容
- `memory_type`: 记忆类型（conversation/fact/preference/task/insight/document）
- `importance`: 重要性评分（1-10）
- `tags`: 标签列表

**注意**：此文件**不管理工具配置**，仅存储用户长期记忆。

### 2.3 tool_index.json 结构

```json
{
  "version": "1.0",
  "updated_at": "2026-03-07 12:56:37",
  "tools": [
    {
      "name": "skill_weather",
      "tool_type": "skill",
      "source": "skills/weather",
      "enabled": true,
      "add_to_memory": true,
      "query_count": 34
    }
  ]
}
```

**字段说明**：
- `name`: 工具名称（唯一标识）
- `tool_type`: 工具类型（builtin/mcp_server/skill/**plugin**）
- `source`: 工具来源路径
- `enabled`: ✅ **工具开关**（false 则禁用）
- `add_to_memory`: ✅ **记忆功能启停**（true 则按需加载）
- `query_count`: 查询次数（热点统计）

### 2.4 配置效果说明

| 配置组合 | 效果 |
|---------|------|
| `enabled: false` | 工具被禁用，不会出现在工具列表中 |
| `enabled: true, add_to_memory: false` | 工具常驻内存，始终可用 |
| `enabled: true, add_to_memory: true` | 工具存入向量DB，通过 search_memory 按需加载 |

---

## 三、插件工具注册到 tool_index.json

插件系统需要将插件工具注册到 `tool_index.json`，实现统一管理：

### 3.1 扩展 tool_type 枚举

```json
{
  "tools": [
    // 现有工具类型
    {
      "name": "file_read",
      "tool_type": "builtin",
      "enabled": true,
      "add_to_memory": false
    },
    {
      "name": "skill_weather",
      "tool_type": "skill",
      "source": "skills/weather",
      "enabled": true,
      "add_to_memory": true
    },
    {
      "name": "mcp_filesystem",
      "tool_type": "mcp_server",
      "mcp_server": "filesystem-server",
      "enabled": true,
      "add_to_memory": false
    },
    
    // 插件工具（新增类型）
    {
      "name": "timer_create",
      "tool_type": "plugin",
      "source": "plugins/timer_plugin",
      "enabled": true,
      "add_to_memory": false
    },
    {
      "name": "timer_list",
      "tool_type": "plugin",
      "source": "plugins/timer_plugin",
      "enabled": true,
      "add_to_memory": true
    }
  ]
}
```

### 3.2 tool_type 类型说明

| tool_type | 说明 | source 格式 |
|-----------|------|------------|
| `builtin` | 内置工具（file/shell等） | 无需 source |
| `skill` | 技能工具 | `skills/{skill_name}` |
| `mcp_server` | MCP 服务工具 | 无需 source，使用 mcp_server 字段 |
| `plugin` | 插件工具（新增） | `plugins/{plugin_name}` |

### 3.3 插件工具的管理操作

**禁用插件工具**：
```json
{
  "name": "timer_create",
  "tool_type": "plugin",
  "enabled": false,
  "add_to_memory": false
}
```

**将插件工具设为按需加载**：
```json
{
  "name": "timer_list",
  "tool_type": "plugin",
  "enabled": true,
  "add_to_memory": true
}
```

---

## 四、插件系统与记忆系统的集成

### 4.1 增强 BasePlugin 接口

```python
class BasePlugin(ABC):
    @property
    def memory_config(self) -> Dict[str, Any]:
        """
        插件工具的记忆配置
        
        Returns:
            Dict: 工具名 -> 记忆配置
            {
                "timer_create": {"add_to_memory": False},  # 常驻，高频使用
                "timer_list": {"add_to_memory": True},     # 按需加载，低频使用
                "timer_cancel": {"add_to_memory": True},   # 按需加载
            }
        """
        return {}
```

### 4.2 增强 PluginManager

```python
class PluginManager:
    def __init__(self, memory_system=None):
        self.memory_system = memory_system
    
    def load_plugin(self, plugin_name: str, config: Dict = None) -> bool:
        # ... 加载插件 ...
        
        # 同步到记忆系统
        if self.memory_system:
            self._sync_to_memory_index(plugin)
        
        return True
    
    def _sync_to_memory_index(self, plugin: BasePlugin):
        """将插件工具同步到记忆索引"""
        for tool_def in plugin.get_tool_definitions():
            tool_name = tool_def.get("name")
            mem_config = plugin.memory_config.get(tool_name, {})
            
            self.memory_system.register_tool(
                name=tool_name,
                description=tool_def.get("description", ""),
                tool_type="plugin",
                source=f"plugins/{plugin.name}",
                add_to_memory=mem_config.get("add_to_memory", True)
            )
```

### 4.3 插件工具的记忆配置示例

```python
class TimerPlugin(BasePlugin):
    @property
    def memory_config(self) -> Dict[str, Any]:
        return {
            # timer_create 高频使用，常驻内存
            "timer_create": {"add_to_memory": False},
            
            # timer_list 和 timer_cancel 低频使用，按需加载
            "timer_list": {"add_to_memory": True},
            "timer_cancel": {"add_to_memory": True},
        }
```

---

## 五、工具类型与记忆配置建议

### 5.1 配置建议

| 工具类型 | add_to_memory | 原因 |
|---------|---------------|------|
| 高频工具 | false | 常驻内存，减少搜索开销 |
| 低频工具 | true | 按需加载，减少 token 消耗 |
| 核心工具 | false | 必须常驻，如 file_read |
| 专业工具 | true | 特定场景才用，如股票分析 |

### 5.2 适合插件化的工具

| 类型 | 示例 | add_to_memory 建议 |
|------|------|-------------------|
| **独立功能模块** | 定时器、闹钟、提醒 | 高频 false，低频 true |
| **外部服务集成** | 天气查询、翻译、地图API | true（按需加载） |
| **数据处理工具** | PDF处理、图片压缩 | true（按需加载） |
| **领域专用工具** | 股票分析、法律查询 | true（按需加载） |

### 5.3 不适合插件化的工具

| 类型 | 示例 | 原因 |
|------|------|------|
| **核心基础设施** | file_read、file_write | Agent 基础能力，必须常驻 |
| **系统级工具** | shell_exec | 核心功能，安全敏感 |
| **记忆系统工具** | save_memory、search_memory | 记忆系统本身的管理工具 |

---

## 六、总结

### 6.1 核心要点

```
tool_index.json 统一管理所有工具：

├── builtin（内置工具）
├── skill（技能工具）
├── mcp_server（MCP服务工具）
└── plugin（插件工具）

配置字段：
├── enabled: true/false     → 工具开关
└── add_to_memory: true/false → 记忆功能启停
```

### 6.2 插件集成记忆系统的步骤

1. 在 `BasePlugin` 中定义 `memory_config` 属性
2. 在 `PluginManager` 中实现 `_sync_to_memory_index` 方法
3. 插件加载时自动同步到 `tool_index.json`
4. 记忆系统根据配置决定工具的加载方式

---

*文档版本：1.0*  
*创建日期：2026-03-07*
