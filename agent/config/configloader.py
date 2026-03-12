# ======================================
# 1. 配置中心（JSON首选 + 默认生成带注释JSON）
# ======================================
import os
import time
from pickle import GLOBAL
import json5
import yaml
from typing import Dict, Any, List, Optional, AsyncGenerator, TypeVar, overload
from loguru import logger

T = TypeVar("T")

class ConfigLoader:
    _instance = None
    FICSBOT_DIR = "./.ficsbot"
    CONFIG_JSON_PATH = "./.ficsbot/config.json"
    CONFIG_YAML_PATH = "./.ficsbot/config.yaml"
    DEFAULT_JSON_TEMPLATE = '''{
    // 基础路径配置（统一存放于 .ficsbot 目录）
    "workspace_root": "./.ficsbot/workspace",
    // 文件操作白名单：仅允许访问这些目录
    "file_allow_list": [
        "./.ficsbot/workspace"
    ],
    // Shell命令白名单：仅允许执行这些命令（为空则不限制，优先级高于黑名单）
    "shell_cmd_whitelist": [],
    // Shell命令黑名单：禁止执行的高危命令（白名单存在时此配置失效）
    "shell_cmd_deny_list": [
        "rm -rf /",
        "dd if=",
        "mkfs",
        ">:(){:|:&};:",
        "sudo",
        "su",
        "chmod 777 /",
        "shutdown",
        "reboot"
    ],
    // Shell路径白名单：仅允许在这些目录执行（为空则不限制，优先级高于黑名单）
    "shell_path_whitelist": [
        "./.ficsbot/workspace"
    ],
    // Shell路径黑名单：禁止在这些目录执行（白名单存在时此配置失效）
    "shell_path_deny_list": [],
    // LLM大模型配置（厂商名=LiteLLM标准前缀）
    "llm": {
        // 全局通用参数（所有模型默认继承，单模型可覆盖）
        "global": {
            "temperature": 0.3,
            "max_tokens": 2048,
            "context_window": 128000,
            "timeout": 60,
            "stream": true,
            "drop_params": true
        },
        // 默认主模型（格式：厂商名/模型别名）
        "default_model": "openai/gpt35",
        // 厂商分组配置，key为LiteLLM标准厂商前缀
        "providers": {
            // OpenAI官方
            "openai": {
                "api_key": "你的OpenAI API Key",
                "api_base": "",
                "models": {
                    "gpt35": {
                        "model_name": "gpt-3.5-turbo",
                        "remark": "OpenAI GPT-3.5 Turbo"
                    },
                    "gpt4o": {
                        "model_name": "gpt-4o",
                        "remark": "OpenAI GPT-4o"
                    }
                }
            },
            // 阿里云通义千问
            "tongyi": {
                "api_key": "你的通义千问API Key",
                "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "models": {
                    "qwen-max": {
                        "remark": "通义千问Max"
                    },
                    "qwen-plus": {
                        "remark": "通义千问Plus"
                    }
                }
            },
            // 本地Ollama模型
            "ollama": {
                "api_key": "ollama",
                "api_base": "http://localhost:11434/v1",
                "models": {
                    "llama3-8b": {
                        "model_name": "llama3:8b",
                        "remark": "本地Llama3 8B"
                    }
                }
            }
        }
    },
    // 对话上下文配置
    "conversation": {
        "max_history_rounds": 10,
        "max_context_tokens": 4000
    },
    // API服务配置
    "api": {
        "host": "0.0.0.0",
        "port": 8000,
        "enable": true
    },
    // 功能开关
    "enable_file_tool": true,
    "enable_shell_tool": true,
    "enable_skill_tool": true,
    "enable_mcp": true,
    // 工具执行超时时间（秒）
    "exec_timeout": 10,
    // 日志配置
    "log": {
        "enable_file": false,
        "log_dir": "./.ficsbot/logs",
        "level": "INFO",
        "console_level": "DEBUG",
        "rotation": "10 MB",
        "retention": "7 days",
        "enable_console": true
    },
    // 会话持久化配置
    "session": {
        "enable_persistence": true,
        "storage_dir": "./.ficsbot/sessions",
        "max_sessions": 100,
        "expire_days": 30,
        "auto_save": true,
        "auto_save_interval": 5
    },
    // 记忆系统配置
    "memory": {
        "enabled": true,
        "db_path": "{workspace_root}/memory/vector_db",
        "index_path": "{workspace_root}/memory/memory_index",
        "hot_threshold": 100,
        "hot_tool_limit": 5,
        "embedding": {
            "provider": "local",
            "local_model": "BAAI/bge-small-zh-v1.5",
            "cache_folder": "{workspace_root}/models/huggingface"
        }
    }
}
'''
    # 无注释的默认配置字典（用于合并兜底）
    DEFAULT_CONFIG = json5.loads(DEFAULT_JSON_TEMPLATE)

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_config()
        return cls._instance

    def _init_config(self):
        init_start = time.time()
        self.current_config_path = None
        self.config_type = None
        self.config = self.DEFAULT_CONFIG.copy()

        load_start = time.time()
        self._load_config()
        load_time = (time.time() - load_start) * 1000

        flatten_start = time.time()
        self._flatten_models = self._build_flatten_models()
        flatten_time = (time.time() - flatten_start) * 1000

        total_time = (time.time() - init_start) * 1000
        logger.debug(f"[ConfigLoader] 配置加载: {load_time:.2f}ms, 模型扁平化: {flatten_time:.2f}ms, 总耗时: {total_time:.2f}ms")

    def _load_config(self):
        """核心加载逻辑：JSON首选，YAML仅次选兼容，无配置生成带注释JSON"""
        user_config = {}
        step_times = {}

        # 1. 优先加载config.json（支持带注释）
        step_start = time.time()
        if os.path.exists(self.CONFIG_JSON_PATH):
            try:
                with open(self.CONFIG_JSON_PATH, "r", encoding="utf-8") as f:
                    user_config = json5.load(f)
                self.current_config_path = self.CONFIG_JSON_PATH
                self.config_type = "json"
                logger.info(f"✅ 已加载配置文件：{self.CONFIG_JSON_PATH} (JSON格式，支持注释)")
            except Exception as e:
                logger.error(f"❌ config.json 解析失败：{str(e)}，请检查格式/注释是否规范")
                return
        # 2. 无JSON则兼容加载config.yaml（仅老用户兼容）
        elif os.path.exists(self.CONFIG_YAML_PATH):
            try:
                with open(self.CONFIG_YAML_PATH, "r", encoding="utf-8") as f:
                    user_config = yaml.safe_load(f) or {}
                self.current_config_path = self.CONFIG_YAML_PATH
                self.config_type = "yaml"
                logger.info(f"✅ 已加载配置文件：{self.CONFIG_YAML_PATH} (YAML格式，仅兼容模式)")
            except Exception as e:
                logger.error(f"❌ config.yaml 解析失败：{str(e)}")
                return
        # 3. 无任何配置文件，生成带注释的默认config.json
        else:
            with open(self.CONFIG_JSON_PATH, "w", encoding="utf-8") as f:
                f.write(self.DEFAULT_JSON_TEMPLATE)
            self.current_config_path = self.CONFIG_JSON_PATH
            self.config_type = "json"
            logger.info(f"✅ 已生成默认配置文件：{self.CONFIG_JSON_PATH} (带注释JSON格式)")
            user_config = self.DEFAULT_CONFIG.copy()
        step_times["load_file"] = (time.time() - step_start) * 1000

        # 4. 合并用户配置与默认配置（兜底缺失项）
        step_start = time.time()
        self.config = self._merge_config(self.DEFAULT_CONFIG, user_config)
        step_times["merge"] = (time.time() - step_start) * 1000

        # 5. 校验默认模型
        step_start = time.time()
        self._validate_default_model()
        step_times["validate"] = (time.time() - step_start) * 1000

        # 6. 自动创建必要目录
        step_start = time.time()
        self._init_dirs()
        step_times["init_dirs"] = (time.time() - step_start) * 1000

        logger.debug(f"[_load_config 详细] load_file={step_times['load_file']:.2f}ms, "
                     f"merge={step_times['merge']:.2f}ms, validate={step_times['validate']:.2f}ms, "
                     f"init_dirs={step_times['init_dirs']:.2f}ms")

    def _merge_config(self, default: Dict, user: Dict) -> Dict:
        """递归合并配置，用户配置覆盖默认值"""
        merged = default.copy()
        for k, v in user.items():
            if isinstance(v, dict) and k in merged and isinstance(merged[k], dict):
                merged[k] = self._merge_config(merged[k], v)
            else:
                merged[k] = v
        return merged

    def _build_flatten_models(self) -> Dict[str, Dict]:
        """把厂商分组配置扁平化为「厂商/模型别名」为key的字典"""
        flatten = {}
        global_config = self.get("llm.global", {})
        providers = self.get("llm.providers", {})

        for provider_name, provider_config in providers.items():
            provider_base_config = {k: v for k, v in provider_config.items() if k != "models"}
            provider_models = provider_config.get("models", {})

            for model_alias, model_config in provider_models.items():
                full_alias = f"{provider_name}/{model_alias}"
                litellm_model_name = f"{provider_name}/{model_config.get('model_name', model_alias)}"
                full_config = {
                    **global_config,
                    **provider_base_config,
                    **model_config,
                    "full_alias": full_alias,
                    "provider": provider_name,
                    "model_alias": model_alias,
                    "litellm_model_name": litellm_model_name
                }
                flatten[full_alias] = full_config
        return flatten

    def _validate_default_model(self):
        """校验默认模型是否存在，不存在则用第一个可用模型兜底"""
        default_model = self.get("llm.default_model")
        flatten_models = self._build_flatten_models()
        if default_model not in flatten_models:
            if len(flatten_models) > 0:
                first_model = list(flatten_models.keys())[0]
                print(f"⚠️  默认模型 {default_model} 不存在，自动切换到：{first_model}")
                self.config["llm"]["default_model"] = first_model
            else:
                raise Exception("配置文件中未配置任何可用模型，请检查llm.providers配置")
        self._flatten_models = flatten_models

    def _init_dirs(self):
        """自动创建必要目录"""
        os.makedirs(self.FICSBOT_DIR, exist_ok=True)
        os.makedirs(self.config["workspace_root"], exist_ok=True)
        os.makedirs(os.path.join(self.config["workspace_root"], "skills"), exist_ok=True)
        os.makedirs(os.path.join(self.config["workspace_root"], "tasks"), exist_ok=True)
        os.makedirs(os.path.join(self.config["workspace_root"], "memory"), exist_ok=True)
        os.makedirs(os.path.join(self.config["workspace_root"], "models"), exist_ok=True)
        log_dir = self.config.get("log", {}).get("log_dir", "./.ficsbot/logs")
        os.makedirs(log_dir, exist_ok=True)
        session_dir = self.config.get("session", {}).get("storage_dir", "./.ficsbot/sessions")
        os.makedirs(session_dir, exist_ok=True)
        for path in self.config.get("file_allow_list", []):
            os.makedirs(path, exist_ok=True)

    def reload(self):
        """热重载配置文件"""
        print(f"🔄 正在重载配置文件：{self.current_config_path}")
        self._load_config()
        print("✅ 配置文件重载完成")

    @overload
    def get(self, key: str) -> Any: ...
    @overload
    def get(self, key: str, default: T) -> T: ...
    def get(self, key: str, default=None):
        """获取配置项，支持点分隔符"""
        keys = key.split(".")
        value = self.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def get_model_config(self, full_alias: str) -> Optional[Dict]:
        """获取指定模型的完整配置"""
        return self._flatten_models.get(full_alias)

    def list_all_models(self) -> Dict[str, Dict]:
        """获取所有已配置的模型列表"""
        return self._flatten_models.copy()


# 全局配置单例
GLOBAL_CONFIG = ConfigLoader()

