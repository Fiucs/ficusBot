# ======================================
# 2. 核心工具类（完全不变）
# ======================================
import os
import shutil
from typing import Dict, Any, List, Optional, AsyncGenerator

from loguru import logger
from agent.config.configloader import GLOBAL_CONFIG 
from agent.fileSystem.path_resolver import PathResolver
from agent.tool.shelltool import ShellTool
from datetime import datetime
import glob


class FileSystemTool:
    """
    文件系统工具类
    
    功能说明：提供安全的文件操作功能，包括文件的创建、读取、写入、删除、搜索等
    
    配置项（通过 config.json 配置）：
    - file_allow_list: 文件操作白名单目录列表
    - workspace_root: 工作区根目录
    
    核心方法：
    - touch/mkdir: 创建文件/目录
    - read/write/append: 读写文件
    - list_dir/stat/exists: 查看目录/文件信息
    - find: 递归搜索文件
    - rename/move/copy: 重命名/移动/复制
    - delete: 删除文件或目录
    """
    
    def __init__(self):
        self.allow_list = [os.path.abspath(p) for p in GLOBAL_CONFIG.get("file_allow_list", [])]
        self.workspace_root = os.path.abspath(GLOBAL_CONFIG.get("workspace_root", "."))
        self.path_resolver = PathResolver(self.allow_list)
        self.shell_tool = ShellTool()

    def _safe_path(self, input_path: str) -> str:
        """
        安全路径解析

        权限校验规则：
        1. 使用 PathResolver 解析路径为绝对路径
        2. allow_list 为空时：不限制，所有路径都可访问
        3. allow_list 有值时：路径必须在白名单内才能访问

        参数:
            input_path: 相对路径（相对于工作区）或绝对路径

        返回:
            绝对路径

        异常:
            PermissionError: 路径不在允许访问的目录内
        """
        resolved_path, suggestion = self.path_resolver.resolve(input_path, self.workspace_root)

        if resolved_path is None:
            error_msg = suggestion if suggestion else f"路径解析失败: {input_path}"
            raise PermissionError(error_msg)

        # PathResolver 始终返回绝对路径
        abs_path = os.path.abspath(resolved_path)

        # 权限校验
        if self.allow_list:
            abs_path_normalized = os.path.abspath(abs_path)
            is_allowed = any(
                abs_path_normalized.startswith(os.path.abspath(allow_path))
                for allow_path in self.allow_list
            )
            if not is_allowed:
                raise PermissionError(f"路径 '{input_path}' 不在允许访问的目录内")

        return abs_path

    def touch(self, file_path: str) -> Dict[str, Any]:
        """
        创建空文件或更新文件时间戳

        参数:
            file_path: 文件路径（相对路径或绝对路径）

        返回:
            status: success/error
            message: 操作结果信息
            path: 文件原始路径
        """
        try:
            safe_path = self._safe_path(file_path)
            os.makedirs(os.path.dirname(safe_path), exist_ok=True)
            with open(safe_path, "a", encoding="utf-8"):
                os.utime(safe_path, None)
            return {"status": "success", "message": f"文件创建成功: {file_path}", "path": file_path}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def mkdir(self, dir_path: str, recursive: bool = True) -> Dict[str, Any]:
        """
        创建目录

        参数:
            dir_path: 目录路径（相对路径或绝对路径）
            recursive: 是否递归创建父目录，默认True

        返回:
            status: success/error
            message: 操作结果信息
            path: 目录原始路径
        """
        try:
            safe_path = self._safe_path(dir_path)
            os.makedirs(safe_path, exist_ok=recursive)
            return {"status": "success", "message": f"目录创建成功: {dir_path}", "path": dir_path}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def read(self, file_path: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """
        读取文件内容

        参数:
            file_path: 文件路径（相对路径或绝对路径）
            encoding: 文件编码，默认utf-8

        返回:
            status: success/error
            content: 文件内容
            path: 文件原始路径
            message: 错误信息（若status为error）
        """
        try:
            safe_path = self._safe_path(file_path)
            if not os.path.isfile(safe_path):
                logger.error(f"文件不存在: {file_path}")
                return {"status": "error", "message": f"文件不存在: {file_path}"}
            with open(safe_path, "r", encoding=encoding) as f:
                content = f.read()
            return {"status": "success", "content": content, "path": file_path}
        except Exception as e:
            logger.error(f"读取文件 {file_path} 时出错: {str(e)}")
            return {"status": "error", "message": str(e)}

    def list_dir(self, dir_path: str = ".", show_hidden: bool = False) -> Dict[str, Any]:
        """
        列出目录内容

        参数:
            dir_path: 目录路径（相对路径或绝对路径），默认当前工作目录
            show_hidden: 是否显示隐藏文件（以.开头），默认False

        返回:
            status: success/error
            path: 目录原始路径
            items: 文件/目录列表，每项包含name、type、size
            message: 错误信息（若status为error）
        """
        try:
            safe_path = self._safe_path(dir_path)
            if not os.path.isdir(safe_path):
                return {"status": "error", "message": f"目录不存在: {dir_path}"}
            items = os.listdir(safe_path)
            if not show_hidden:
                items = [item for item in items if not item.startswith(".")]
            result = []
            for item in items:
                item_path = os.path.join(safe_path, item)
                result.append({
                    "name": item,
                    "type": "dir" if os.path.isdir(item_path) else "file",
                    "size": os.path.getsize(item_path) if os.path.isfile(item_path) else None
                })
            return {"status": "success", "path": dir_path, "items": result}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def stat(self, path: str) -> Dict[str, Any]:
        """
        获取文件或目录的详细信息

        参数:
            path: 文件/目录路径（相对路径或绝对路径）

        返回:
            status: success/error
            path: 原始路径
            type: 类型（file/dir）
            size: 文件大小（字节），目录为None
            create_time: 创建时间（ISO格式）
            modify_time: 修改时间（ISO格式）
            permission: 权限（八进制如755）
            message: 错误信息（若status为error）
        """
        try:
            safe_path = self._safe_path(path)
            if not os.path.exists(safe_path):
                return {"status": "error", "message": f"路径不存在: {path}"}
            stat_info = os.stat(safe_path)
            return {
                "status": "success",
                "path": path,
                "type": "dir" if os.path.isdir(safe_path) else "file",
                "size": stat_info.st_size,
                "create_time": datetime.fromtimestamp(stat_info.st_ctime).isoformat(),
                "modify_time": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
                "permission": oct(stat_info.st_mode)[-3:]
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def exists(self, path: str) -> Dict[str, Any]:
        """
        检查路径是否存在及类型

        参数:
            path: 文件/目录路径（相对路径或绝对路径）

        返回:
            status: success/error
            exists: 是否存在
            type: 类型（file/dir），不存在时为None
            path: 原始路径
            message: 错误信息（若status为error）
        """
        try:
            safe_path = self._safe_path(path)
            is_exists = os.path.exists(safe_path)
            return {
                "status": "success",
                "exists": is_exists,
                "type": "dir" if is_exists and os.path.isdir(safe_path) else "file" if is_exists else None,
                "path": path
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def find(self, root_path: str = ".", pattern: str = "*", file_type: str = "all", content_keyword: Optional[str] = None) -> Dict[str, Any]:
        """
        递归搜索文件或目录

        参数:
            root_path: 搜索起始目录路径（相对路径或绝对路径），默认当前工作目录
            pattern: 文件名匹配模式（支持通配符，如 "*.py", "test*"）
            file_type: 过滤类型，可选值:
                - "all": 所有文件和目录（默认）
                - "file": 仅文件
                - "dir": 仅目录
            content_keyword: 文件内容关键词过滤（仅对文件有效）

        返回:
            包含搜索结果的字典:
            - status: "success" 或 "error"
            - root_path: 搜索的根目录（原始路径）
            - matched_count: 匹配到的数量
            - paths: 匹配路径列表（相对于工作区的相对路径）
            - message: 错误信息（若 status 为 error）

        示例:
            find("src", "*.py")                    # 搜索 src 目录下所有 .py 文件
            find(".", "*.txt", "file")             # 搜索所有 txt 文件
            find(".", "*", "dir")                  # 搜索所有目录
            find(".", "*.py", "file", "class")     # 搜索包含 "class" 关键词的 .py 文件
        """
        try:
            # 1. 安全路径校验：将相对路径转换为绝对路径
            safe_root = self._safe_path(root_path)
            if not os.path.isdir(safe_root):
                return {"status": "error", "message": f"根目录不存在: {root_path}"}
            
            # 2. 构建搜索模式：使用 ** 实现递归匹配
            search_pattern = os.path.join(safe_root, "**", pattern)
            matched_paths = glob.glob(search_pattern, recursive=True)
            
            # 3. 按类型过滤（文件或目录）
            if file_type == "file":
                matched_paths = [p for p in matched_paths if os.path.isfile(p)]
            elif file_type == "dir":
                matched_paths = [p for p in matched_paths if os.path.isdir(p)]
            
            # 4. 按内容关键词过滤（仅对文件有效）
            if content_keyword and file_type != "dir":
                filtered = []
                for p in matched_paths:
                    if os.path.isfile(p):
                        try:
                            with open(p, "r", encoding="utf-8") as f:
                                if content_keyword in f.read():
                                    filtered.append(p)
                        except:
                            continue
                matched_paths = filtered
            
            # 5. 转换为相对于工作区的路径并返回结果
            relative_paths = [os.path.relpath(p, self.workspace_root) for p in matched_paths]
            return {"status": "success", "root_path": root_path, "matched_count": len(relative_paths), "paths": relative_paths}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def write(self, file_path: str, content: str, encoding: str = "utf-8", overwrite: bool = True) -> Dict[str, Any]:
        """
        写入文件内容（覆盖模式）

        参数:
            file_path: 文件路径（相对路径或绝对路径）
            content: 要写入的内容
            encoding: 文件编码，默认utf-8
            overwrite: 是否覆盖已存在文件，默认True

        返回:
            status: success/error
            message: 操作结果信息
            path: 文件原始路径
            size: 写入内容长度
            message: 错误信息（若status为error）
        """
        try:
            safe_path = self._safe_path(file_path)
            if not overwrite and os.path.exists(safe_path):
                return {"status": "error", "message": f"文件已存在，禁止覆盖: {file_path}"}
            os.makedirs(os.path.dirname(safe_path), exist_ok=True)
            with open(safe_path, "w", encoding=encoding) as f:
                f.write(content)
            return {"status": "success", "message": f"文件写入成功: {file_path}", "path": file_path, "size": len(content)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def append(self, file_path: str, content: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """
        追加内容到文件末尾

        参数:
            file_path: 文件路径（相对路径或绝对路径）
            content: 追加的内容
            encoding: 文件编码，默认utf-8

        返回:
            status: success/error
            message: 操作结果信息
            path: 文件原始路径
            message: 错误信息（若status为error）
        """
        try:
            safe_path = self._safe_path(file_path)
            os.makedirs(os.path.dirname(safe_path), exist_ok=True)
            with open(safe_path, "a", encoding=encoding) as f:
                f.write(content)
            return {"status": "success", "message": f"内容追加成功: {file_path}", "path": file_path}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def rename(self, old_path: str, new_path: str) -> Dict[str, Any]:
        """
        重命名文件或目录

        参数:
            old_path: 原路径（相对路径或绝对路径）
            new_path: 新路径（相对路径或绝对路径）

        返回:
            status: success/error
            message: 操作结果信息
            message: 错误信息（若status为error）
        """
        try:
            safe_old = self._safe_path(old_path)
            safe_new = self._safe_path(new_path)
            if not os.path.exists(safe_old):
                return {"status": "error", "message": f"原路径不存在: {old_path}"}
            os.rename(safe_old, safe_new)
            return {"status": "success", "message": f"重命名成功: {old_path} → {new_path}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def move(self, source_path: str, target_path: str) -> Dict[str, Any]:
        """
        移动文件或目录到目标位置

        参数:
            source_path: 源路径（相对路径或绝对路径）
            target_path: 目标路径（相对路径或绝对路径）

        返回:
            status: success/error
            message: 操作结果信息
            message: 错误信息（若status为error）
        """
        try:
            safe_source = self._safe_path(source_path)
            safe_target = self._safe_path(target_path)
            if not os.path.exists(safe_source):
                return {"status": "error", "message": f"源路径不存在: {source_path}"}
            os.makedirs(os.path.dirname(safe_target), exist_ok=True)
            shutil.move(safe_source, safe_target)
            return {"status": "success", "message": f"移动成功: {source_path} → {target_path}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def copy(self, source_path: str, target_path: str, overwrite: bool = False) -> Dict[str, Any]:
        """
        复制文件或目录

        参数:
            source_path: 源路径（相对路径或绝对路径）
            target_path: 目标路径（相对路径或绝对路径）
            overwrite: 是否覆盖已存在文件，默认False

        返回:
            status: success/error
            message: 操作结果信息
            message: 错误信息（若status为error）
        """
        try:
            safe_source = self._safe_path(source_path)
            safe_target = self._safe_path(target_path)
            if not os.path.exists(safe_source):
                return {"status": "error", "message": f"源路径不存在: {source_path}"}
            if os.path.exists(safe_target) and not overwrite:
                return {"status": "error", "message": f"目标路径已存在，禁止覆盖: {target_path}"}
            if os.path.isdir(safe_source):
                shutil.copytree(safe_source, safe_target, dirs_exist_ok=overwrite)
            else:
                os.makedirs(os.path.dirname(safe_target), exist_ok=True)
                shutil.copy2(safe_source, safe_target)
            return {"status": "success", "message": f"复制成功: {source_path} → {target_path}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def delete(self, path: str, recursive: bool = False, force: bool = False) -> Dict[str, Any]:
        """
        删除文件或目录

        参数:
            path: 文件/目录路径（相对路径或绝对路径）
            recursive: 删除目录时是否递归删除子目录，默认False
            force: 强制删除目录（忽略recursive），默认False

        返回:
            status: success/error
            message: 操作结果信息
            message: 错误信息（若status为error）

        注意:
            - 无法删除工作区根目录
            - 删除目录需要 recursive=True 或 force=True
        """
        try:
            safe_path = self._safe_path(path)
            if not os.path.exists(safe_path):
                return {"status": "error", "message": f"路径不存在: {path}"}
            if safe_path == os.path.abspath(GLOBAL_CONFIG.get("workspace_root")):
                return {"status": "error", "message": "禁止删除工作区根目录"}
            if os.path.isfile(safe_path):
                os.remove(safe_path)
                return {"status": "success", "message": f"文件删除成功: {path}"}
            if os.path.isdir(safe_path):
                if not recursive and not force:
                    return {"status": "error", "message": f"目录删除需开启recursive=True: {path}"}
                shutil.rmtree(safe_path)
                return {"status": "success", "message": f"目录删除成功: {path}"}
            return {"status": "error", "message": "不支持的路径类型"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_system_folder(self, folder_name: str) -> Dict[str, Any]:
        """
        获取系统特殊文件夹路径（桌面、下载、文档、图片、视频、音乐等）
        
        功能说明：根据文件夹名称获取 Windows 系统的常用文件夹绝对路径。
        获取的路径可用于后续的文件搜索、读取等操作。
        
        参数:
            folder_name: 文件夹名称，支持中英文:
                - "Desktop" / "桌面": 桌面
                - "Downloads" / "下载": 下载
                - "Documents" / "文档": 文档
                - "Pictures" / "图片": 图片
                - "Videos" / "视频": 视频
                - "Music" / "音乐": 音乐
                - "UserProfile" / "用户目录": 用户主目录
                
        返回:
            status: success/error
            folder_name: 请求的文件夹名称
            path: 文件夹的绝对路径
            message: 错误信息（若status为error）
            
        示例:
            get_system_folder("Desktop")     # 获取桌面路径
            get_system_folder("桌面")         # 获取桌面路径（中文）
            get_system_folder("Downloads")   # 获取下载文件夹路径
            get_system_folder("下载")         # 获取下载文件夹路径（中文）
        """
        try:
            # 标准化文件夹名称
            folder_name = folder_name.strip()
            
            # 中文名称映射到英文名称
            chinese_to_english = {
                "桌面": "Desktop",
                "下载": "Downloads",
                "文档": "Documents",
                "图片": "Pictures",
                "视频": "Videos",
                "音乐": "Music",
                "用户目录": "UserProfile",
            }
            
            # 如果是中文名称，转换为英文
            if folder_name in chinese_to_english:
                folder_name = chinese_to_english[folder_name]
            
            # Windows 特殊文件夹名称映射（PowerShell Environment.GetFolderPath 参数）
            windows_folders = {
                "Desktop": "Desktop",
                "Downloads": "UserProfile",  # Downloads 需要特殊处理
                "Documents": "MyDocuments",
                "Pictures": "MyPictures",
                "Videos": "MyVideos",
                "Music": "MyMusic",
                "UserProfile": "UserProfile",
            }
            
            if folder_name not in windows_folders:
                supported = "Desktop(桌面), Downloads(下载), Documents(文档), Pictures(图片), Videos(视频), Music(音乐), UserProfile(用户目录)"
                return {
                    "status": "error", 
                    "message": f"不支持的文件夹名称: {folder_name}。支持的名称: {supported}"
                }
            
            # 使用 ShellTool 执行 PowerShell 命令获取文件夹路径
            ps_folder = windows_folders[folder_name]
            cmd = f'powershell -Command "[Environment]::GetFolderPath(\'{ps_folder}\')"'
            result = self.shell_tool.exec(cmd)
            
            if result.get("status") != "success":
                return {"status": "error", "message": f"获取文件夹路径失败: {result.get('stderr', result.get('message', '未知错误'))}"}
            
            folder_path = result.get("stdout", "").strip()
            
            # Downloads 文件夹特殊处理（在 UserProfile 下）
            if folder_name == "Downloads":
                downloads_path = os.path.join(folder_path, "Downloads")
                if os.path.exists(downloads_path):
                    folder_path = downloads_path
            
            if not folder_path or not os.path.exists(folder_path):
                return {"status": "error", "message": f"文件夹不存在: {folder_name}"}
            
            return {
                "status": "success",
                "folder_name": folder_name,
                "path": folder_path
            }
                
        except Exception as e:
            return {"status": "error", "message": str(e)}
