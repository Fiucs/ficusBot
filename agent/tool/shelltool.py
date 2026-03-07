import os
import sys
import subprocess
from typing import Any, Dict, Optional, TYPE_CHECKING
from loguru import logger
from agent.config.configloader import GLOBAL_CONFIG
from agent.utils.command_utils import CommandQuoteHelper

if TYPE_CHECKING:
    from agent.config.agent_config import AgentConfig


class ShellTool:
    """
    Shell命令执行工具类
    
    功能说明：
    - 提供安全的Shell命令执行功能
    - 支持命令黑白名单过滤
    - 支持路径黑白名单过滤
    - 自动适配Windows/Linux平台
    - 自动修复命令中的引号嵌套问题
    
    配置项（通过config.json配置）：
    - shell_cmd_whitelist: 命令白名单（为空不限制，优先级高于黑名单）
    - shell_cmd_deny_list: 命令黑名单
    - shell_path_whitelist: 路径白名单（为空不限制，优先级高于黑名单）
    - shell_path_deny_list: 路径黑名单
    - exec_timeout: 命令执行超时时间（秒）
    - workspace_root: 工作区根目录
    """
    
    def __init__(self, agent_config: Optional["AgentConfig"] = None):
        """
        初始化ShellTool，加载配置项
        
        Args:
            agent_config: Agent 配置对象，支持 Agent 级别配置覆盖全局配置
        """
        self.agent_config = agent_config
        if agent_config:
            self.cmd_whitelist = agent_config.get_shell_cmd_whitelist()
            self.cmd_deny_list = agent_config.get_shell_cmd_deny_list()
            self.path_whitelist = agent_config.get_shell_path_whitelist()
            self.path_deny_list = agent_config.get_shell_path_deny_list()
            self.timeout = agent_config.get_exec_timeout()
            self.workspace_root = os.path.abspath(agent_config.get_workspace_root())
        else:
            self.cmd_whitelist = GLOBAL_CONFIG.get("shell_cmd_whitelist", [])
            self.cmd_deny_list = GLOBAL_CONFIG.get("shell_cmd_deny_list", [])
            self.path_whitelist = GLOBAL_CONFIG.get("shell_path_whitelist", [])
            self.path_deny_list = GLOBAL_CONFIG.get("shell_path_deny_list", [])
            self.timeout = GLOBAL_CONFIG.get("exec_timeout", 10)
            self.workspace_root = os.path.abspath(GLOBAL_CONFIG.get("workspace_root", "."))
        self.is_windows = sys.platform.startswith("win")

    def _wrap_windows_cmd(self, cmd: str) -> str:
        """
        Windows平台命令包装
        
        Args:
            cmd: 原始命令
            
        Returns:
            包装后的命令，Windows下自动添加cmd /c前缀
        """
        if self.is_windows and not cmd.strip().lower().startswith("cmd /c"):
            return f"cmd /c {cmd}"
        return cmd

    def _check_cmd(self, cmd: str) -> Dict[str, Any]:
        """
        检查命令是否允许执行
        
        Args:
            cmd: 待执行的命令
            
        Returns:
            None表示允许执行，Dict表示拒绝执行及错误信息
        """
        import re
        cmd_lower = cmd.lower()
        
        if self.cmd_whitelist:
            for allow_cmd in self.cmd_whitelist:
                if allow_cmd.lower() in cmd_lower:
                    return None
            return {"status": "error", "message": f"命令不在白名单内，禁止执行: {cmd}"}
        
        if self.cmd_deny_list:
            for deny_cmd in self.cmd_deny_list:
                deny_cmd_lower = deny_cmd.lower()
                # 使用单词边界匹配，避免误判（如 "su" 不会匹配 "mcporter" 中的 "exa-full"）
                pattern = r'\b' + re.escape(deny_cmd_lower) + r'\b'
                if re.search(pattern, cmd_lower):
                    return {"status": "error", "message": f"高危命令已拦截: {deny_cmd}"}
        
        return None

    def _check_path(self, cwd: str) -> Dict[str, Any]:
        """
        检查工作目录是否允许执行
        
        Args:
            cwd: 工作目录路径
            
        Returns:
            None表示允许执行，Dict表示拒绝执行及错误信息
        """
        abs_cwd = os.path.abspath(os.path.join(self.workspace_root, cwd))
        
        if self.path_whitelist:
            for allow_path in self.path_whitelist:
                if abs_cwd.startswith(os.path.abspath(allow_path)):
                    return None
            return {"status": "error", "message": f"工作目录不在白名单内，禁止执行: {cwd}"}
        
        if self.path_deny_list:
            for deny_path in self.path_deny_list:
                if abs_cwd.startswith(os.path.abspath(deny_path)):
                    return {"status": "error", "message": f"工作目录在黑名单中，禁止执行: {deny_path}"}
        
        return None

    def exec(self, cmd: str, cwd: str = ".") -> Dict[str, Any]:
        """
        执行Shell命令
        
        执行流程：
        1. 检查命令是否在黑白名单中
        2. 检查工作目录是否在黑白名单中
        3. 修复命令中的引号嵌套问题
        4. 执行命令并返回结果
        
        Args:
            cmd: 待执行的命令
            cwd: 工作目录，默认为当前目录
            
        Returns:
            执行结果字典，包含status、stdout、stderr、returncode、cmd字段
        """
        cmd_check = self._check_cmd(cmd)
        if cmd_check:
            return cmd_check
        
        path_check = self._check_path(cwd)
        if path_check:
            return path_check
        
        # 修复命令中的引号嵌套问题
        original_cmd = cmd
        if self.is_windows:
            # Windows 下修复命令的引号问题
            cmd = CommandQuoteHelper.fix_mcp_command(cmd)
            
            logger.info(f"引号修复: '{original_cmd}' -> '{cmd}'")
        
        
        
        try:
            safe_cwd = os.path.abspath(os.path.join(self.workspace_root, cwd))
            
            if self.is_windows:
                wrapped_cmd = self._wrap_windows_cmd(cmd)
                result = subprocess.run(
                    wrapped_cmd,
                    cwd=safe_cwd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    shell=True
                )
            else:
                result = subprocess.run(
                    cmd,
                    cwd=safe_cwd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    shell=True
                )
            return {
                "status": "success" if result.returncode == 0 else "error",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "cmd": cmd,
                "original_cmd": original_cmd if original_cmd != cmd else None
            }
        except Exception as e:
            return {"status": "error", "message": f"命令执行失败: {str(e)}, 命令: {cmd}"}
