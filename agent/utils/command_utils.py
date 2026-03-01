"""
命令行引号处理工具类。

解决 Windows/PowerShell 环境下命令行参数中引号嵌套的问题。
例如：mcporter call 'exa.web_search_exa(query: "黄金金价 当前价格", numResults: 5)'
"""

import re
import shlex
from typing import Optional, Tuple


class CommandQuoteHelper:
    """
    命令行引号处理工具类。
    
    功能说明:
        - 处理命令行参数中的引号嵌套问题
        - 支持 Windows PowerShell 和 CMD 环境
        - 提供引号转义和规范化功能
    
    核心方法:
        - fix_nested_quotes: 修复嵌套引号问题
        - escape_for_shell: 为 Shell 执行转义字符串
        - normalize_command: 规范化命令字符串
    
    使用场景:
        - 当命令参数中包含单引号和双引号嵌套时
        - 例如: mcporter call 'exa.web_search_exa(query: "黄金金价", numResults: 5)'
    """
    
    @staticmethod
    def fix_nested_quotes(command: str) -> str:
        """
        修复命令中的嵌套引号问题。
        
        将外层单引号转换为双引号，内层双引号转义为 \\"
        适用于 PowerShell 和 CMD 环境。
        
        Args:
            command: 原始命令字符串
            
        Returns:
            修复后的命令字符串
            
        示例:
            >>> CommandQuoteHelper.fix_nested_quotes(
            ...     "mcporter call 'exa.web_search_exa(query: \\"黄金金价\\", numResults: 5)'"
            ... )
            'mcporter call "exa.web_search_exa(query: \\"黄金金价\\", numResults: 5)"'
        """
        if not command:
            return command
        
        result = command
        
        # 模式1: 外层单引号，内层双引号
        # 例如: 'exa.web_search_exa(query: "黄金金价")' -> "exa.web_search_exa(query: \"黄金金价\")"
        pattern1 = r"'([^']*(?:\"[^\"]*\")[^']*)'"
        
        def replace_single_outer(match):
            inner = match.group(1)
            # 转义内层双引号
            inner_escaped = inner.replace('"', '\\"')
            return f'"{inner_escaped}"'
        
        result = re.sub(pattern1, replace_single_outer, result)
        
        return result
    
    @staticmethod
    def escape_for_shell(text: str, shell_type: str = "powershell") -> str:
        """
        为 Shell 执行转义字符串。
        
        Args:
            text: 需要转义的文本
            shell_type: Shell 类型，支持 "powershell" 或 "cmd"
            
        Returns:
            转义后的文本
            
        示例:
            >>> CommandQuoteHelper.escape_for_shell('黄金金价 "当前"', 'powershell')
            '黄金金价 \\"当前\\"'
        """
        if not text:
            return text
        
        if shell_type == "powershell":
            # PowerShell 转义规则
            # 1. 双引号需要用反引号或反斜杠转义
            text = text.replace('"', '`"')
            # 2. 美元符号需要转义
            text = text.replace('$', '`$')
            # 3. 反引号本身需要转义
            text = text.replace('`', '``')
        elif shell_type == "cmd":
            # CMD 转义规则
            # 1. 双引号需要用反斜杠转义
            text = text.replace('"', '\\"')
            # 2. 百分号需要双写
            text = text.replace('%', '%%')
        
        return text
    
    @staticmethod
    def normalize_command(command: str) -> str:
        """
        规范化命令字符串。
        
        处理以下问题:
        1. 多余的空格
        2. 引号不匹配
        3. 嵌套引号
        
        Args:
            command: 原始命令字符串
            
        Returns:
            规范化后的命令字符串
        """
        if not command:
            return command
        
        result = command.strip()
        
        # 移除多余空格（保留引号内的空格）
        parts = []
        in_quotes = False
        quote_char = None
        current = []
        
        for char in result:
            if char in '"\'':
                if not in_quotes:
                    in_quotes = True
                    quote_char = char
                elif char == quote_char:
                    in_quotes = False
                    quote_char = None
                current.append(char)
            elif char == ' ' and not in_quotes:
                if current:
                    parts.append(''.join(current))
                    current = []
            else:
                current.append(char)
        
        if current:
            parts.append(''.join(current))
        
        result = ' '.join(parts)
        
        # 修复嵌套引号
        result = CommandQuoteHelper.fix_nested_quotes(result)
        
        return result
    
    @staticmethod
    def wrap_argument(arg: str, quote_char: str = '"') -> str:
        """
        为参数添加引号包裹。
        
        如果参数包含空格或特殊字符，则用引号包裹。
        
        Args:
            arg: 参数值
            quote_char: 引号类型，默认双引号
            
        Returns:
            包裹后的参数
        """
        if not arg:
            return arg
        
        # 检查是否需要引号
        needs_quotes = any(c in arg for c in ' \t\n\r"\'<>|&()[]{}')
        
        if needs_quotes:
            # 如果参数中已包含该引号，先转义
            if quote_char in arg:
                arg = arg.replace(quote_char, '\\' + quote_char)
            return f"{quote_char}{arg}{quote_char}"
        
        return arg
    
    @staticmethod
    def parse_command_with_quotes(command: str) -> Tuple[str, list]:
        """
        解析命令字符串，正确处理引号内的内容。
        
        Args:
            command: 命令字符串
            
        Returns:
            元组 (命令名, 参数列表)
            
        示例:
            >>> CommandQuoteHelper.parse_command_with_quotes(
            ...     'mcporter call "exa.web_search_exa(query: \\"黄金金价\\")"'
            ... )
            ('mcporter', ['call', 'exa.web_search_exa(query: "黄金金价")'])
        """
        if not command:
            return ('', [])
        
        try:
            # 使用 shlex 进行智能分割
            # 对于 Windows，需要特殊处理
            parts = shlex.split(command, posix=False)
            
            # 清理引号
            cleaned_parts = []
            for part in parts:
                # 移除外层引号
                if (part.startswith('"') and part.endswith('"')) or \
                   (part.startswith("'") and part.endswith("'")):
                    part = part[1:-1]
                cleaned_parts.append(part)
            
            if cleaned_parts:
                return (cleaned_parts[0], cleaned_parts[1:])
            return ('', [])
            
        except ValueError:
            # shlex 解析失败，回退到简单分割
            parts = command.split()
            if parts:
                return (parts[0], parts[1:])
            return ('', [])
    
    @staticmethod
    def fix_mcp_command(command: str) -> str:
        """
        修复命令中的引号问题（通用版本）。
        
        处理规则:
        - CMD 不识别单引号作为字符串分隔符，需要转换为双引号
        - 外层单引号 → 双引号
        - 内层双引号 → 转义双引号 \"
        
        Args:
            command: 命令字符串
            
        Returns:
            修复后的命令字符串
        """
        if not command:
            return command
        
        result = command
        
        # 模式1: 单引号包裹且内层包含双引号
        # 例如: 'xxx(param: "yyy")' → "xxx(param: \"yyy\")"
        pattern1 = r"'([^']*(?:\"[^\"]*\")[^']*)'"
        
        def fix_quoted_with_inner_quotes(match):
            content = match.group(1)
            # 先移除已有的转义字符（避免双重转义）
            content = content.replace(r'\"', '"')
            # 然后转义双引号
            if '"' in content:
                content = content.replace('"', r'\"')
            return f'"{content}"'
        
        result = re.sub(pattern1, fix_quoted_with_inner_quotes, result)
        
        # 模式2: 单引号包裹但不包含双引号（简单转换）
        # 例如: 'simple_arg' → "simple_arg"
        # 注意：要避免匹配已经被模式1处理过的内容
        pattern2 = r"'([^']+)'"
        
        def fix_simple_quoted(match):
            content = match.group(1)
            # 如果内容包含空格或特殊字符，用双引号包裹
            if ' ' in content or '(' in content:
                return f'"{content}"'
            return match.group(0)  # 保持原样
        
        result = re.sub(pattern2, fix_simple_quoted, result)
        
        return result


if __name__ == "__main__":
    # 测试命令
    test_command = "mcporter call 'exa.web_search_exa(query: \"黄金金价 当前价格\", numResults: 5)'"
    fixed_command = CommandQuoteHelper.fix_mcp_command(test_command)
    print(f"原始命令: {test_command}")
    print(f"修复后的命令: {fixed_command}")