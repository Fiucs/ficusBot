"""
浏览器自动化工具模块

功能说明:
    - 提供浏览器自动化操作能力
    - 支持页面导航、元素交互、内容提取等
    - 通过 register_to_tool_adapter 与 ToolAdapter 集成
    - 支持异步操作和同步调用包装

核心方法:
    - start: 启动浏览器
    - close: 关闭浏览器
    - navigate: 导航到指定 URL
    - click: 点击指定索引的元素
    - input_text: 在指定元素中输入文本
    - scroll: 滚动页面
    - extract: 提取页面内容
    - screenshot: 截图
    - send_keys: 发送按键
    - go_back: 返回上一页
    - get_state: 获取页面状态

配置项（通过 config.json 配置）:
    - browser_headless: 无头模式，默认 True
    - browser_stealth: 反检测模式，默认 True
    - browser_timeout: 操作超时时间，默认 30 秒
    - browser_window_width: 窗口宽度，默认 1280
    - browser_window_height: 窗口高度，默认 800
    - enable_browser: 是否启用浏览器功能，默认 True

使用示例:
    from agent.tool.browsertool import BrowserTool
    
    browser = BrowserTool()
    browser.register_to_tool_adapter(tool_adapter)
    
    result = browser.navigate(url="https://example.com")
    result = browser.click(index=5)
    result = browser.input_text(index=10, text="Hello World")
"""

import asyncio
import base64
import concurrent.futures
from typing import Dict, Any, List, Optional
from loguru import logger
from colorama import Fore, Style

from agent.config.configloader import GLOBAL_CONFIG


class BrowserTool:
    """
    Browser automation tool (Singleton pattern).
    
    Features:
        - Provides browser automation capabilities
        - Supports page navigation, element interaction, content extraction
        - Integrates with ToolAdapter via register_to_tool_adapter
        - Supports async operations with sync wrapper
        - Singleton pattern ensures single browser instance across sessions
    
    Core methods:
        - start: Start browser
        - close: Close browser
        - navigate: Navigate to URL
        - click: Click element by index
        - input_text: Input text into element
        - scroll: Scroll page
        - extract: Extract page content
        - screenshot: Take screenshot
        - send_keys: Send keyboard keys
        - go_back: Go back to previous page
        - get_state: Get page state
    
    Config options:
        - browser_headless: Headless mode, default True
        - browser_timeout: Operation timeout in seconds, default 30
        - browser_window_width: Window width, default 1280
        - browser_window_height: Window height, default 800
        - browser_max_iframes: Max iframe count, default 10
        - browser_wait_time: Wait time between actions, default 0.05
        - browser_state_mode: State extraction mode, default "interactive"
        - browser_max_elements: Max elements in state, default 20
        - browser_prioritize_visible: Only visible elements, default True
        - browser_max_text_length: Max text length per element, default 30
        - browser_include_page_summary: Include page summary, default True
        - browser_summary_max_length: Max summary length, default 300
    
    Usage:
        browser = BrowserTool.get_instance()
        browser.register_to_tool_adapter(tool_adapter)
        
        result = await browser.navigate(url="https://example.com")
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def get_instance(cls):
        """Get singleton instance of BrowserTool."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        """
        Initialize browser tool (only once due to singleton pattern).
        
        Config options:
            - browser_headless: Headless mode, default True
            - browser_timeout: Operation timeout in seconds, default 30
            - browser_window_width: Window width, default 1280
            - browser_window_height: Window height, default 800
            - browser_max_iframes: Max iframe count, default 10
            - browser_wait_time: Wait time between actions, default 0.05
        """
        if BrowserTool._initialized:
            return
        
        self._browser = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
        self._headless = GLOBAL_CONFIG.get("browser_headless", True)
        self._timeout = GLOBAL_CONFIG.get("browser_timeout", 30)
        self._window_width = GLOBAL_CONFIG.get("browser_window_width", 1280)
        self._window_height = GLOBAL_CONFIG.get("browser_window_height", 800)
        self._max_iframes = GLOBAL_CONFIG.get("browser_max_iframes", 10)
        self._wait_time = GLOBAL_CONFIG.get("browser_wait_time", 0.05)
        
        self._state_mode = GLOBAL_CONFIG.get("browser_state_mode", "interactive")
        self._max_elements = GLOBAL_CONFIG.get("browser_max_elements", 20)
        self._prioritize_visible = GLOBAL_CONFIG.get("browser_prioritize_visible", True)
        self._max_text_length = GLOBAL_CONFIG.get("browser_max_text_length", 30)
        self._include_page_summary = GLOBAL_CONFIG.get("browser_include_page_summary", True)
        self._summary_max_length = GLOBAL_CONFIG.get("browser_summary_max_length", 300)
        
        self._is_started = False
        self._current_url = ""
        
        BrowserTool._initialized = True
        logger.info(f"{Fore.CYAN}[Browser] Initialized, headless={self._headless}, window={self._window_width}x{self._window_height}, max_iframes={self._max_iframes}, state_mode={self._state_mode}, max_elements={self._max_elements}{Style.RESET_ALL}")
    
    def _get_event_loop(self) -> asyncio.AbstractEventLoop:
        """
        获取或创建事件循环
        
        返回:
            asyncio.AbstractEventLoop: 事件循环对象
        """
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_event_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop
    
    def _run_async(self, coro):
        """
        同步运行异步协程（参考 MCPManager._run_async 实现）
        
        参数:
            coro: 异步协程对象
            
        返回:
            协程执行结果
        """
        loop = self._get_event_loop()
        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
    
    def _make_caller(self, method_name: str):
        """
        创建工具调用函数（包装异步方法为同步）
        
        参数:
            method_name: 方法名称
            
        返回:
            同步调用函数
        """
        def caller(**kwargs):
            method = getattr(self, method_name)
            if asyncio.iscoroutinefunction(method):
                return self._run_async(method(**kwargs))
            return method(**kwargs)
        return caller
    
    def _get_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Get tool definitions list
        
        Returns:
            List of tool definitions, each containing name, method, description, parameters
        """
        return [
            {
                "name": "browser.navigate",
                "method": "navigate",
                "description": "Navigate to URL. Open webpage. Params: url(required). Ex: browser.navigate({url:'https://example.com'})",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Target URL"}
                    },
                    "required": ["url"]
                }
            },
            {
                "name": "browser.click",
                "method": "click",
                "description": "Click element by index. Params: index(required, element index from page state). Ex: browser.click({index:5})",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer", "description": "Element index from page state"}
                    },
                    "required": ["index"]
                }
            },
            {
                "name": "browser.input",
                "method": "input_text",
                "description": "Input text into element. Params: index(required), text(required), clear(optional, default true). Ex: browser.input({index:10, text:'hello'})",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer", "description": "Element index"},
                        "text": {"type": "string", "description": "Text to input"},
                        "clear": {"type": "boolean", "description": "Clear input first", "default": True}
                    },
                    "required": ["index", "text"]
                }
            },
            {
                "name": "browser.scroll",
                "method": "scroll",
                "description": "Scroll page. Params: direction(optional, up/down, default down), pages(optional, default 1). Ex: browser.scroll({direction:'down', pages:1})",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "direction": {"type": "string", "enum": ["up", "down"], "description": "Scroll direction", "default": "down"},
                        "pages": {"type": "number", "description": "Number of pages to scroll", "default": 1.0}
                    },
                    "required": []
                }
            },
            {
                "name": "browser.extract",
                "method": "extract",
                "description": "Extract page content as plain text. Use format='markdown' only if user explicitly needs markdown format. Ex: browser.extract({}) or browser.extract({selector:'article'})",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "CSS selector (optional, extract full page if empty)"},
                        "format": {"type": "string", "enum": ["text", "markdown"], "description": "Output format (default: text). Use markdown only when explicitly needed.", "default": "text"}
                    },
                    "required": []
                }
            },
            # 截图工具已禁用，截图走另外的方案
            # {
            #     "name": "browser.screenshot",
            #     "method": "screenshot",
            #     "description": "Take screenshot. Params: path(optional, save path). Returns base64 image. Ex: browser.screenshot({})",
            #     "parameters": {
            #         "type": "object",
            #         "properties": {
            #             "path": {"type": "string", "description": "Screenshot save path (optional)"}
            #         },
            #         "required": []
            #     }
            # },
            {
                "name": "browser.send_keys",
                "method": "send_keys",
                "description": "Send keyboard keys. Params: keys(required). Ex: browser.send_keys({keys:'Enter'}) or browser.send_keys({keys:'Control+A'})",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keys": {"type": "string", "description": "Key sequence, e.g. Enter, Tab, Escape, Control+A"}
                    },
                    "required": ["keys"]
                }
            },
            {
                "name": "browser.go_back",
                "method": "go_back",
                "description": "Go back to previous page. No params. Ex: browser.go_back({})",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "browser.get_state",
                "method": "get_state",
                "description": "Get page state with clickable elements. Returns URL, title, element list and page summary. Token-optimized with configurable mode.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "mode": {
                            "type": "string", 
                            "enum": ["interactive", "minimal", "full"], 
                            "description": "Extraction mode: interactive(only interactive elements), minimal(essential elements only), full(all elements). Default: interactive",
                            "default": "interactive"
                        },
                        "max_elements": {
                            "type": "integer", 
                            "description": "Max elements to return (default: 20, range: 5-50)",
                            "default": 20
                        },
                        "prioritize_visible": {
                            "type": "boolean", 
                            "description": "Only include viewport-visible elements (default: true)",
                            "default": True
                        },
                        "include_summary": {
                            "type": "boolean", 
                            "description": "Include page text summary (default: true)",
                            "default": True
                        }
                    },
                    "required": []
                }
            },
            {
                "name": "browser.switch_tab",
                "method": "switch_tab",
                "description": "Switch to tab by index. Params: tab_index(required). Ex: browser.switch_tab({tab_index:1})",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tab_index": {"type": "integer", "description": "Tab index (start from 0)"}
                    },
                    "required": ["tab_index"]
                }
            },
            {
                "name": "browser.close_tab",
                "method": "close_tab",
                "description": "Close current tab. No params. Ex: browser.close_tab({})",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "browser.list_tabs",
                "method": "list_tabs",
                "description": "List all open tabs. No params. Ex: browser.list_tabs({})",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        ]
    
    def register_to_tool_adapter(self, tool_adapter) -> int:
        """
        将浏览器工具注册到 ToolAdapter（参考 MCPToolAdapter 实现）
        
        参数:
            tool_adapter: ToolAdapter 实例
            
        返回:
            注册的工具数量
        """
        count = 0
        for tool_def in self._get_tool_definitions():
            tool_adapter.tools[tool_def["name"]] = {
                "name": tool_def["name"],
                "func": self._make_caller(tool_def["method"]),
                "description": tool_def["description"],
                "parameters": tool_def["parameters"]
            }
            count += 1
        
        if count > 0:
            logger.info(f"{Fore.CYAN}[Browser] 已注册 {count} 个浏览器工具到 ToolAdapter{Style.RESET_ALL}")
        
        return count
    
    async def _ensure_browser_started(self) -> Dict[str, Any]:
        """
        确保浏览器已启动
        
        返回:
            启动结果字典
        """
        if self._is_started and self._browser:
            try:
                page = await self._browser.get_current_page()
                if page:
                    return {"status": "success", "message": "浏览器已在运行"}
            except Exception as e:
                error_str = str(e).lower()
                if any(keyword in error_str for keyword in ["close frame", "websocket", "connection", "closed", "disconnected", "target closed", "keepalive", "ping timeout", "1011"]):
                    logger.warning(f"{Fore.YELLOW}[Browser] 浏览器连接断开 ({e})，正在重启...{Style.RESET_ALL}")
                    self._browser = None
                    self._is_started = False
                else:
                    logger.warning(f"{Fore.YELLOW}[Browser] 浏览器连接异常 ({e})，正在重启...{Style.RESET_ALL}")
                    self._browser = None
                    self._is_started = False
        
        return await self.start()
    
    async def start(self) -> Dict[str, Any]:
        """
        启动浏览器（Token 优化配置）
        
        返回:
            操作结果字典，包含 status 和 message
        """
        try:
            from browser_use import BrowserSession
            
            logger.info(f"{Fore.CYAN}[Browser] 正在启动浏览器...{Style.RESET_ALL}")
            
            self._browser = BrowserSession(
                headless=self._headless,
                window_size={"width": self._window_width, "height": self._window_height},
                highlight_elements=False,
                max_iframes=self._max_iframes,
                max_iframe_depth=3,
                wait_between_actions=self._wait_time
            )
            await self._browser.start()
            
            self._is_started = True
            
            logger.info(f"{Fore.GREEN}[Browser] 浏览器启动成功 ({self._window_width}x{self._window_height}, max_iframes={self._max_iframes}){Style.RESET_ALL}")
            
            return {
                "status": "success",
                "message": "浏览器启动成功"
            }
            
        except ImportError as e:
            error_msg = f"browser-use 未安装: {e}"
            logger.error(f"{Fore.RED}[Browser] {error_msg}{Style.RESET_ALL}")
            return {
                "status": "error",
                "message": error_msg,
                "hint": "请运行: pip install browser-use playwright && playwright install chromium"
            }
        except Exception as e:
            error_msg = f"浏览器启动失败: {str(e)}"
            logger.error(f"{Fore.RED}[Browser] {error_msg}{Style.RESET_ALL}")
            return {
                "status": "error",
                "message": error_msg
            }
    
    async def close(self) -> Dict[str, Any]:
        """
        关闭浏览器
        
        返回:
            操作结果字典，包含 status 和 message
        """
        if not self._is_started or not self._browser:
            return {"status": "success", "message": "浏览器未运行"}
        
        try:
            logger.info(f"{Fore.CYAN}[Browser] 正在关闭浏览器...{Style.RESET_ALL}")
            
            await asyncio.sleep(0.1)
            
            try:
                await self._browser.stop()
            except Exception:
                await self._browser.kill()
            
            await asyncio.sleep(0.1)
            
            self._browser = None
            self._is_started = False
            self._current_url = ""
            
            if self._loop and not self._loop.is_closed():
                try:
                    pending = asyncio.all_tasks(self._loop)
                    for task in pending:
                        if not task.done():
                            task.cancel()
                except Exception:
                    pass
            
            logger.info(f"{Fore.GREEN}[Browser] 浏览器已关闭{Style.RESET_ALL}")
            
            return {
                "status": "success",
                "message": "浏览器已关闭"
            }
            
        except Exception as e:
            error_msg = f"关闭浏览器失败: {str(e)}"
            logger.error(f"{Fore.RED}[Browser] {error_msg}{Style.RESET_ALL}")
            self._browser = None
            self._is_started = False
            self._current_url = ""
            return {
                "status": "error",
                "message": error_msg
            }
    
    async def navigate(self, url: str) -> Dict[str, Any]:
        """
        Navigate to URL. Opens new tab if needed.
        
        Args:
            url: Target URL
            
        Returns:
            Result dict with status, message, url, title
        """
        await self._ensure_browser_started()
        
        if not self._browser:
            return {"status": "error", "message": "Browser not initialized"}
        
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        
        url = url.strip().strip('`').strip('"').strip("'")
        
        from urllib.parse import urlparse, unquote
        
        parsed_target = urlparse(url)
        target_domain = parsed_target.netloc
        
        for attempt in range(2):
            try:
                current_url = await self._browser.get_current_page_url()
                current_title = await self._browser.get_current_page_title()
                
                current_decoded = unquote(current_url) if current_url else ""
                target_decoded = unquote(url)
                
                if current_url and current_url != "about:blank":
                    if target_decoded in current_decoded or current_decoded in target_decoded:
                        logger.info(f"{Fore.CYAN}[Browser] Already on target page: {url}{Style.RESET_ALL}")
                        return {
                            "status": "success",
                            "message": f"Already on page: {url}",
                            "url": current_url,
                            "title": current_title
                        }
                    
                    logger.info(f"{Fore.CYAN}[Browser] Current page has content, opening new tab: {url}{Style.RESET_ALL}")
                    try:
                        from browser_use.browser.events import SwitchTabEvent
                        
                        page_targets_before = self._browser.session_manager.get_all_page_targets() if self._browser.session_manager else []
                        
                        new_page = await self._browser.new_page(url)
                        if new_page:
                            await asyncio.sleep(0.5)
                            
                            page_targets_after = self._browser.session_manager.get_all_page_targets() if self._browser.session_manager else []
                            
                            if len(page_targets_after) > len(page_targets_before):
                                new_target = page_targets_after[-1]
                                await self._browser.event_bus.dispatch(SwitchTabEvent(target_id=new_target.target_id))
                                await asyncio.sleep(0.3)
                            
                            logger.info(f"{Fore.CYAN}[Browser] Opened in new tab{Style.RESET_ALL}")
                    except Exception as e:
                        logger.warning(f"{Fore.YELLOW}[Browser] new_page failed: {e}, using navigate_to{Style.RESET_ALL}")
                        await self._browser.navigate_to(url)
                else:
                    logger.info(f"{Fore.CYAN}[Browser] Current page is blank, navigating in current tab: {url}{Style.RESET_ALL}")
                    await self._browser.navigate_to(url)
                
                self._current_url = url
                
                await asyncio.sleep(1.0)
                
                title = await self._browser.get_current_page_title()
                actual_url = await self._browser.get_current_page_url()
                
                if actual_url == "about:blank":
                    logger.warning(f"{Fore.YELLOW}[Browser] Page still blank, retrying...{Style.RESET_ALL}")
                    page = await self._browser.get_current_page()
                    if page:
                        await page.navigate(url)
                        title = await self._browser.get_current_page_title()
                        actual_url = await self._browser.get_current_page_url()
                
                logger.info(f"{Fore.GREEN}[Browser] Navigation success: {title} ({actual_url}){Style.RESET_ALL}")
                
                return {
                    "status": "success",
                    "message": f"Navigated to: {url}",
                    "url": actual_url,
                    "title": title
                }
                
            except Exception as e:
                error_str = str(e).lower()
                if any(keyword in error_str for keyword in ["keepalive", "ping timeout", "websocket", "connectionclosed", "closed", "1011", "disconnect"]):
                    if attempt == 0:
                        logger.warning(f"{Fore.YELLOW}[Browser] Connection lost, reconnecting...{Style.RESET_ALL}")
                        self._browser = None
                        self._is_started = False
                        await self.start()
                        continue
                error_msg = f"Navigation failed: {str(e)}"
                logger.error(f"{Fore.RED}[Browser] {error_msg}{Style.RESET_ALL}")
                return {
                    "status": "error",
                    "message": error_msg
                }
        
        return {"status": "error", "message": "Navigation failed: cannot connect to browser"}
    
    async def click(self, index: int) -> Dict[str, Any]:
        """
        点击指定索引的元素
        
        参数:
            index: 元素索引（从页面状态获取）
            
        返回:
            操作结果字典
        """
        await self._ensure_browser_started()
        
        if not self._browser:
            return {"status": "error", "message": "浏览器未初始化"}
        
        try:
            logger.info(f"{Fore.CYAN}[Browser] 正在点击元素 [{index}]{Style.RESET_ALL}")
            
            page = await self._browser.get_current_page()
            if not page:
                return {"status": "error", "message": "无法获取当前页面"}
            
            clicked = await page.evaluate(f"""
                () => {{
                    const results = [];
                    const seen = new Set();
                    const MAX_ELEMENTS = 20;
                    
                    // 屏蔽广告/冗余模块选择器
                    const excludeSelectors = [
                        'script', 'style', 'noscript', 'svg', 'iframe',
                        '.ad', '.advertisement', '.ads', '.ad-container',
                        '.recommend', '.feed', '.sidebar', '.side-bar',
                        '#content_right', '.footer', '.modal', '.popup',
                        '[aria-hidden="true"]', '.hidden', '.hide'
                    ];
                    
                    const isExcluded = (el) => {{
                        for (const selector of excludeSelectors) {{
                            if (el.closest(selector)) return true;
                            try {{
                                if (el.matches && el.matches(selector)) return true;
                            }} catch(e) {{}}
                        }}
                        return false;
                    }};
                    
                    const isVisible = (el) => {{
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) return false;
                        const style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden') return false;
                        return true;
                    }};
                    
                    const addElement = (el, priority) => {{
                        if (results.length >= MAX_ELEMENTS) return;
                        if (isExcluded(el)) return;
                        if (!isVisible(el)) return;
                        
                        const text = (el.innerText || el.value || el.placeholder || '').substring(0, 30).trim();
                        const id = el.id || '';
                        const className = (el.className || '').toString().substring(0, 20);
                        const key = el.tagName + text + id + className;
                        
                        if (!seen.has(key)) {{
                            seen.add(key);
                            results.push({{el: el, priority: priority}});
                        }}
                    }};
                    
                    const inputs = document.querySelectorAll('input[type="text"], input[type="search"], input:not([type]), textarea');
                    inputs.forEach(el => addElement(el, 1));
                    
                    const buttons = document.querySelectorAll('button, input[type="submit"], input[type="button"], [role="button"]');
                    buttons.forEach(el => addElement(el, 2));
                    
                    const mainLinks = document.querySelectorAll('nav a, [role="navigation"] a, .nav a, #nav a, .menu a');
                    mainLinks.forEach(el => addElement(el, 3));
                    
                    const allLinks = document.querySelectorAll('a[href]');
                    allLinks.forEach(el => addElement(el, 4));
                    
                    results.sort((a, b) => a.priority - b.priority);
                    
                    if ({index} < results.length) {{
                        results[{index}].el.click();
                        return true;
                    }}
                    return false;
                }}
            """)
            
            if clicked:
                await asyncio.sleep(0.5)
                logger.info(f"{Fore.GREEN}[Browser] 点击成功{Style.RESET_ALL}")
                return {
                    "status": "success",
                    "message": f"已点击元素 [{index}]"
                }
            else:
                return {
                    "status": "error",
                    "message": f"元素索引 {index} 不存在或不可点击"
                }
            
        except Exception as e:
            error_msg = f"点击失败: {str(e)}"
            logger.error(f"{Fore.RED}[Browser] {error_msg}{Style.RESET_ALL}")
            return {
                "status": "error",
                "message": error_msg
            }
    
    async def input_text(self, index: int, text: str, clear: bool = True) -> Dict[str, Any]:
        """
        在指定元素中输入文本
        
        参数:
            index: 元素索引
            text: 要输入的文本
            clear: 是否先清空输入框，默认 True
            
        返回:
            操作结果字典
        """
        await self._ensure_browser_started()
        
        if not self._browser:
            return {"status": "error", "message": "浏览器未初始化"}
        
        try:
            logger.info(f"{Fore.CYAN}[Browser] 正在输入文本到元素 [{index}]{Style.RESET_ALL}")
            
            page = await self._browser.get_current_page()
            if not page:
                return {"status": "error", "message": "无法获取当前页面"}
            
            escaped_text = text.replace("\\", "\\\\").replace('"', '\\"')
            
            inputted = await page.evaluate(f"""
                () => {{
                    const results = [];
                    const seen = new Set();
                    const MAX_ELEMENTS = 20;
                    
                    // 屏蔽广告/冗余模块选择器
                    const excludeSelectors = [
                        'script', 'style', 'noscript', 'svg', 'iframe',
                        '.ad', '.advertisement', '.ads', '.ad-container',
                        '.recommend', '.feed', '.sidebar', '.side-bar',
                        '#content_right', '.footer', '.modal', '.popup',
                        '[aria-hidden="true"]', '.hidden', '.hide'
                    ];
                    
                    const isExcluded = (el) => {{
                        for (const selector of excludeSelectors) {{
                            if (el.closest(selector)) return true;
                            try {{
                                if (el.matches && el.matches(selector)) return true;
                            }} catch(e) {{}}
                        }}
                        return false;
                    }};
                    
                    const isVisible = (el) => {{
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) return false;
                        const style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden') return false;
                        return true;
                    }};
                    
                    const addElement = (el, priority) => {{
                        if (results.length >= MAX_ELEMENTS) return;
                        if (isExcluded(el)) return;
                        if (!isVisible(el)) return;
                        
                        const text = (el.innerText || el.value || el.placeholder || '').substring(0, 30).trim();
                        const id = el.id || '';
                        const className = (el.className || '').toString().substring(0, 20);
                        const key = el.tagName + text + id + className;
                        
                        if (!seen.has(key)) {{
                            seen.add(key);
                            results.push({{el: el, priority: priority}});
                        }}
                    }};
                    
                    const inputs = document.querySelectorAll('input[type="text"], input[type="search"], input:not([type]), textarea');
                    inputs.forEach(el => addElement(el, 1));
                    
                    const buttons = document.querySelectorAll('button, input[type="submit"], input[type="button"], [role="button"]');
                    buttons.forEach(el => addElement(el, 2));
                    
                    const mainLinks = document.querySelectorAll('nav a, [role="navigation"] a, .nav a, #nav a, .menu a');
                    mainLinks.forEach(el => addElement(el, 3));
                    
                    const allLinks = document.querySelectorAll('a[href]');
                    allLinks.forEach(el => addElement(el, 4));
                    
                    results.sort((a, b) => a.priority - b.priority);
                    
                    if ({index} < results.length) {{
                        const el = results[{index}].el;
                        if ({"true"} && el.value) {{
                            el.value = '';
                        }}
                        el.value = "{escaped_text}";
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        return true;
                    }}
                    return false;
                }}
            """)
            
            if inputted:
                logger.info(f"{Fore.GREEN}[Browser] 输入成功{Style.RESET_ALL}")
                return {
                    "status": "success",
                    "message": f"已在元素 [{index}] 中输入文本"
                }
            else:
                return {
                    "status": "error",
                    "message": f"元素索引 {index} 不存在或不可输入"
                }
            
        except Exception as e:
            error_msg = f"输入失败: {str(e)}"
            logger.error(f"{Fore.RED}[Browser] {error_msg}{Style.RESET_ALL}")
            return {
                "status": "error",
                "message": error_msg
            }
    
    async def scroll(self, direction: str = "down", pages: float = 1.0) -> Dict[str, Any]:
        """
        滚动页面
        
        参数:
            direction: 滚动方向，"up" 或 "down"，默认 "down"
            pages: 滚动页数，默认 1.0
            
        返回:
            操作结果字典
        """
        await self._ensure_browser_started()
        
        if not self._browser:
            return {"status": "error", "message": "浏览器未初始化"}
        
        try:
            logger.info(f"{Fore.CYAN}[Browser] 正在滚动页面: {direction} {pages} 页{Style.RESET_ALL}")
            
            page = await self._browser.get_current_page()
            if not page:
                return {"status": "error", "message": "无法获取当前页面"}
            
            viewport_height = 800
            try:
                viewport_height_str = await page.evaluate("() => window.innerHeight")
                if viewport_height_str:
                    viewport_height = int(viewport_height_str)
            except:
                pass
            
            scroll_amount = viewport_height * pages
            
            if direction == "up":
                scroll_amount = -scroll_amount
            
            await page.evaluate(f"() => window.scrollBy(0, {scroll_amount})")
            
            await asyncio.sleep(0.3)
            
            logger.info(f"{Fore.GREEN}[Browser] 滚动成功{Style.RESET_ALL}")
            
            return {
                "status": "success",
                "message": f"已滚动 {direction} {pages} 页"
            }
            
        except Exception as e:
            error_msg = f"滚动失败: {str(e)}"
            logger.error(f"{Fore.RED}[Browser] {error_msg}{Style.RESET_ALL}")
            return {
                "status": "error",
                "message": error_msg
            }
    
    async def extract(self, selector: str = None, format: str = "text") -> Dict[str, Any]:
        """
        Extract page content in text or markdown format.
        
        Args:
            selector: CSS selector, extract full page if empty
            format: Output format - "text" or "markdown" (default: "text")
            
        Returns:
            Result dict with extracted content
        """
        await self._ensure_browser_started()
        
        if not self._browser:
            return {"status": "error", "message": "Browser not initialized"}
        
        try:
            logger.info(f"{Fore.CYAN}[Browser] Extracting page content (format: {format}){Style.RESET_ALL}")
            
            page = await self._browser.get_current_page()
            if not page:
                return {"status": "error", "message": "Cannot get current page"}
            
            if format == "markdown":
                content = await page.evaluate("""
                    () => {
                        const toMarkdown = (el) => {
                            if (!el) return '';
                            
                            if (el.nodeType === Node.TEXT_NODE) {
                                const text = el.textContent || '';
                                return text.trim();
                            }
                            
                            if (el.nodeType !== Node.ELEMENT_NODE) {
                                return '';
                            }
                            
                            const tag = (el.tagName || '').toLowerCase();
                            const children = Array.from(el.childNodes);
                            
                            if (tag === 'script' || tag === 'style' || tag === 'noscript' || tag === 'svg') {
                                return '';
                            }
                            
                            let result = '';
                            
                            for (const child of children) {
                                result += toMarkdown(child);
                            }
                            
                            switch (tag) {
                                case 'h1':
                                    return '\\n# ' + result + '\\n\\n';
                                case 'h2':
                                    return '\\n## ' + result + '\\n\\n';
                                case 'h3':
                                    return '\\n### ' + result + '\\n\\n';
                                case 'h4':
                                    return '\\n#### ' + result + '\\n\\n';
                                case 'h5':
                                    return '\\n##### ' + result + '\\n\\n';
                                case 'h6':
                                    return '\\n###### ' + result + '\\n\\n';
                                case 'p':
                                    return '\\n' + result + '\\n\\n';
                                case 'br':
                                    return '\\n';
                                case 'hr':
                                    return '\\n---\\n\\n';
                                case 'a':
                                    const href = el.getAttribute('href') || '';
                                    return '[' + result + '](' + href + ')';
                                case 'img':
                                    const src = el.getAttribute('src') || '';
                                    const alt = el.getAttribute('alt') || '';
                                    return '![' + alt + '](' + src + ')';
                                case 'ul':
                                    return '\\n' + result + '\\n';
                                case 'ol':
                                    return '\\n' + result + '\\n';
                                case 'li':
                                    const parent = el.parentElement;
                                    if (parent && parent.tagName && parent.tagName.toLowerCase() === 'ol') {
                                        const index = Array.from(parent.children).indexOf(el) + 1;
                                        return index + '. ' + result + '\\n';
                                    }
                                    return '- ' + result + '\\n';
                                case 'blockquote':
                                    return '\\n> ' + result.replace(/\\n/g, '\\n> ') + '\\n\\n';
                                case 'code':
                                    if (el.parentElement && el.parentElement.tagName && el.parentElement.tagName.toLowerCase() === 'pre') {
                                        return '\\n```\\n' + result + '\\n```\\n\\n';
                                    }
                                    return '`' + result + '`';
                                case 'pre':
                                    return result;
                                case 'strong':
                                case 'b':
                                    return '**' + result + '**';
                                case 'em':
                                case 'i':
                                    return '*' + result + '*';
                                case 'table':
                                    return '\\n' + result + '\\n';
                                case 'thead':
                                    return result;
                                case 'tbody':
                                    return result;
                                case 'tr':
                                    return '| ' + result + '\\n';
                                case 'th':
                                case 'td':
                                    return (result || ' ') + ' | ';
                                default:
                                    return result;
                            }
                        };
                        
                        return toMarkdown(document.body).replace(/\\n{3,}/g, '\\n\\n').trim();
                    }
                """)
            elif selector:
                elements = await page.query_selector_all(selector)
                content_parts = []
                for el in elements:
                    try:
                        text = await el.evaluate("() => this.textContent || ''")
                        if text:
                            content_parts.append(text.strip())
                    except:
                        pass
                content = "\n".join(content_parts)
            else:
                content = await page.evaluate("() => document.body.innerText")
            
            content = content.strip() if content else ""
            
            max_length = 8000
            if len(content) > max_length:
                content = content[:max_length] + "\n...(content truncated)"
            
            logger.info(f"{Fore.GREEN}[Browser] Extract success, length: {len(content)}{Style.RESET_ALL}")
            
            return {
                "status": "success",
                "message": "Content extracted successfully",
                "content": content,
                "length": len(content),
                "format": format
            }
            
        except Exception as e:
            error_msg = f"Extract failed: {str(e)}"
            logger.error(f"{Fore.RED}[Browser] {error_msg}{Style.RESET_ALL}")
            return {
                "status": "error",
                "message": error_msg
            }
    
    async def screenshot(self, path: str = None) -> Dict[str, Any]:
        """
        截图
        
        参数:
            path: 截图保存路径（可选）
            
        返回:
            操作结果字典，包含 base64 编码的截图
        """
        await self._ensure_browser_started()
        
        if not self._browser:
            return {"status": "error", "message": "浏览器未初始化"}
        
        try:
            logger.info(f"{Fore.CYAN}[Browser] 正在截图...{Style.RESET_ALL}")
            
            screenshot_bytes = await self._browser.take_screenshot()
            
            screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            
            if path:
                with open(path, "wb") as f:
                    f.write(screenshot_bytes)
                logger.info(f"{Fore.GREEN}[Browser] 截图已保存: {path}{Style.RESET_ALL}")
            
            return {
                "status": "success",
                "message": "截图成功",
                "screenshot": screenshot_base64,
                "path": path
            }
            
        except Exception as e:
            error_msg = f"截图失败: {str(e)}"
            logger.error(f"{Fore.RED}[Browser] {error_msg}{Style.RESET_ALL}")
            return {
                "status": "error",
                "message": error_msg
            }
    
    async def send_keys(self, keys: str) -> Dict[str, Any]:
        """
        发送按键
        
        参数:
            keys: 按键序列，如 "Enter", "Tab", "Escape", "Control+A" 等
            
        返回:
            操作结果字典
        """
        await self._ensure_browser_started()
        
        if not self._browser:
            return {"status": "error", "message": "浏览器未初始化"}
        
        try:
            logger.info(f"{Fore.CYAN}[Browser] 正在发送按键: {keys}{Style.RESET_ALL}")
            
            page = await self._browser.get_current_page()
            if not page:
                return {"status": "error", "message": "无法获取当前页面"}
            
            await page.press(keys)
            
            await asyncio.sleep(0.3)
            
            logger.info(f"{Fore.GREEN}[Browser] 按键发送成功{Style.RESET_ALL}")
            
            return {
                "status": "success",
                "message": f"已发送按键: {keys}"
            }
            
        except Exception as e:
            error_msg = f"发送按键失败: {str(e)}"
            logger.error(f"{Fore.RED}[Browser] {error_msg}{Style.RESET_ALL}")
            return {
                "status": "error",
                "message": error_msg
            }
    
    async def go_back(self) -> Dict[str, Any]:
        """
        返回上一页
        
        返回:
            操作结果字典
        """
        await self._ensure_browser_started()
        
        if not self._browser:
            return {"status": "error", "message": "浏览器未初始化"}
        
        try:
            logger.info(f"{Fore.CYAN}[Browser] 正在返回上一页...{Style.RESET_ALL}")
            
            page = await self._browser.get_current_page()
            if not page:
                return {"status": "error", "message": "无法获取当前页面"}
            
            await page.go_back()
            
            await asyncio.sleep(0.5)
            
            url = await self._browser.get_current_page_url()
            title = await self._browser.get_current_page_title()
            
            logger.info(f"{Fore.GREEN}[Browser] 已返回上一页: {title}{Style.RESET_ALL}")
            
            return {
                "status": "success",
                "message": "已返回上一页",
                "url": url,
                "title": title
            }
            
        except Exception as e:
            error_msg = f"返回失败: {str(e)}"
            logger.error(f"{Fore.RED}[Browser] {error_msg}{Style.RESET_ALL}")
            return {
                "status": "error",
                "message": error_msg
            }
    
    async def get_state(
        self,
        mode: str = None,
        max_elements: int = None,
        prioritize_visible: bool = None,
        include_summary: bool = None
    ) -> Dict[str, Any]:
        """
        获取页面状态（Token 优化版）
        
        参数:
            mode: 提取模式
                - "interactive": 只返回可交互元素（按钮、链接、输入框等）- 推荐，最省 token
                - "minimal": 只返回关键元素（主要导航、主要按钮）
                - "full": 返回所有可点击元素（消耗最多 token）
            max_elements: 最大返回元素数量 (5-50)，默认使用配置值
            prioritize_visible: 是否只返回视口可见元素，默认 True
            include_summary: 是否包含页面文本摘要，默认 True
            
        返回:
            操作结果字典，包含精简的页面状态信息
            
        Token 优化策略:
            - interactive 模式可减少 60-80% token
            - prioritize_visible=True 只返回当前可见元素
            - max_elements 限制返回数量
            - include_summary=False 可进一步减少 token
        """
        actual_mode = mode or self._state_mode
        actual_max_elements = max_elements or self._max_elements
        actual_prioritize_visible = prioritize_visible if prioritize_visible is not None else self._prioritize_visible
        actual_include_summary = include_summary if include_summary is not None else self._include_page_summary
        
        actual_max_elements = max(5, min(50, actual_max_elements))
        
        for attempt in range(2):
            await self._ensure_browser_started()
            
            if not self._browser:
                return {"status": "error", "message": "浏览器未初始化"}
            
            try:
                logger.info(f"{Fore.CYAN}[Browser] Getting page state (mode={actual_mode}, max_elements={actual_max_elements}, visible={actual_prioritize_visible})...{Style.RESET_ALL}")
                
                try:
                    cdp = self._browser.cdp_client
                    if cdp:
                        targets_result = await cdp.send.Target.getTargets()
                        cdp_targets = [t for t in targets_result.get('targetInfos', []) if t.get('type') == 'page']
                        
                        visible_target_id = None
                        visible_title = ""
                        
                        for target in cdp_targets:
                            target_id = target.get('targetId')
                            
                            try:
                                session = await cdp.send.Target.attachToTarget({
                                    "targetId": target_id,
                                    "flatten": True
                                })
                                session_id = session.get('sessionId')
                                
                                await cdp.send.Runtime.enable({}, session_id=session_id)
                                
                                result = await cdp.send.Runtime.evaluate({
                                    "expression": "document.visibilityState",
                                    "returnByValue": True
                                }, session_id=session_id)
                                
                                visibility = result.get('result', {}).get('value', 'hidden')
                                
                                await cdp.send.Runtime.disable({}, session_id=session_id)
                                
                                if visibility == 'visible':
                                    visible_target_id = target_id
                                    visible_title = target.get('title', '')
                                    break
                            except Exception:
                                pass
                        
                        if visible_target_id:
                            current_tracked = self._browser.session_manager.get_focused_target() if self._browser.session_manager else None
                            tracked_id = current_tracked.target_id if current_tracked else None
                            
                            if visible_target_id != tracked_id:
                                logger.info(f"{Fore.CYAN}[Browser] 检测到用户切换了标签页，同步到: {visible_title}{Style.RESET_ALL}")
                                from browser_use.browser.events import SwitchTabEvent
                                await self._browser.event_bus.dispatch(SwitchTabEvent(target_id=visible_target_id))
                                await asyncio.sleep(0.2)
                except Exception as e:
                    logger.warning(f"{Fore.YELLOW}[Browser] 检测可见标签页失败: {e}{Style.RESET_ALL}")
                
                url = await self._browser.get_current_page_url()
                title = await self._browser.get_current_page_title()
                
                logger.info(f"{Fore.CYAN}[Browser] Current page: {url} - {title}{Style.RESET_ALL}")
                
                page = await self._browser.get_current_page()
                if not page:
                    return {"status": "error", "message": "无法获取当前页面"}
                
                if url == "about:blank" or "Starting agent" in title:
                    logger.warning(f"{Fore.YELLOW}[Browser] Page not loaded properly, URL is about:blank{Style.RESET_ALL}")
                    return {
                        "status": "error",
                        "message": "页面未加载，请先导航到 URL",
                        "url": url,
                        "title": title
                    }
                
                js_script = self._build_state_extraction_script(
                    actual_mode, 
                    actual_max_elements, 
                    actual_prioritize_visible,
                    actual_include_summary
                )
                
                page_data = await page.evaluate(js_script)
                
                if isinstance(page_data, str):
                    import json
                    page_data = json.loads(page_data)
                
                if not isinstance(page_data, dict):
                    return {"status": "error", "message": f"页面数据格式错误: {type(page_data)}"}
                
                elements_list = page_data.get("elements", [])
                elements_summary = "\n".join(elements_list) if elements_list else "无可交互元素"
                
                page_state = f"""URL: {url}
标题: {title}

可操作元素 ({len(elements_list)} 个):
{elements_summary}"""
                
                if actual_include_summary and page_data.get("bodyText"):
                    page_state += f"\n\n页面摘要:\n{page_data['bodyText']}"
                
                result = {
                    "status": "success",
                    "message": "页面状态获取成功",
                    "url": url,
                    "title": title,
                    "page_state": page_state,
                    "elements_count": len(elements_list),
                    "mode": actual_mode,
                    "stats": {
                        "inputs": page_data.get("total_inputs", 0),
                        "buttons": page_data.get("total_buttons", 0),
                        "links": page_data.get("total_links", 0)
                    }
                }
                
                logger.info(f"{Fore.GREEN}[Browser] 状态获取成功，共 {len(elements_list)} 个元素 (mode={actual_mode}){Style.RESET_ALL}")
                
                return result
                
            except Exception as e:
                error_str = str(e).lower()
                if any(keyword in error_str for keyword in ["close frame", "websocket", "connection", "closed", "disconnected", "target closed", "keepalive", "ping timeout", "1011"]):
                    if attempt == 0:
                        logger.warning(f"{Fore.YELLOW}[Browser] 连接断开，正在重连...{Style.RESET_ALL}")
                        self._browser = None
                        self._is_started = False
                        continue
                error_msg = f"获取状态失败: {str(e)}"
                logger.error(f"{Fore.RED}[Browser] {error_msg}{Style.RESET_ALL}")
                return {
                    "status": "error",
                    "message": error_msg
                }
        
        return {"status": "error", "message": "获取状态失败: 无法连接到浏览器"}
    
    def _build_state_extraction_script(
        self, 
        mode: str, 
        max_elements: int, 
        prioritize_visible: bool,
        include_summary: bool
    ) -> str:
        """
        构建状态提取的 JavaScript 脚本
        
        参数:
            mode: 提取模式
            max_elements: 最大元素数量
            prioritize_visible: 是否只返回可见元素
            include_summary: 是否包含页面摘要
            
        返回:
            JavaScript 脚本字符串
        """
        mode_config = {
            "interactive": {
                "selectors": [
                    ("input[type='text'], input[type='search'], input:not([type]), textarea", 1),
                    ("button, input[type='submit'], input[type='button'], [role='button']", 2),
                    ("select, [role='listbox'], [role='combobox']", 2),
                    ("a[href]", 3),
                    ("[onclick], [role='link'], [role='menuitem']", 3),
                ],
                "exclude_non_interactive": True
            },
            "minimal": {
                "selectors": [
                    ("input[type='text'], input[type='search'], input:not([type]), textarea", 1),
                    ("button, input[type='submit'], input[type='button']", 2),
                    ("nav a, [role='navigation'] a, .nav a, #nav a, .menu a", 3),
                    ("a[href]:not([href*='#']):not([href*='javascript'])", 4),
                ],
                "exclude_non_interactive": True
            },
            "full": {
                "selectors": [
                    ("input, textarea, select", 1),
                    ("button, [role='button']", 2),
                    ("a[href]", 3),
                    ("[onclick], [role='link']", 4),
                    ("[tabindex]:not([tabindex='-1'])", 5),
                ],
                "exclude_non_interactive": False
            }
        }
        
        config = mode_config.get(mode, mode_config["interactive"])
        selectors_js = "[" + ", ".join([f'["{sel}", {pri}]' for sel, pri in config["selectors"]]) + "]"
        exclude_non_interactive = "true" if config["exclude_non_interactive"] else "false"
        prioritize_visible_js = "true" if prioritize_visible else "false"
        include_summary_js = "true" if include_summary else "false"
        
        return f"""
            () => {{
                const results = [];
                const seen = new Set();
                const MAX_ELEMENTS = {max_elements};
                const PRIORITIZE_VISIBLE = {prioritize_visible_js};
                const INCLUDE_SUMMARY = {include_summary_js};
                const SUMMARY_MAX_LENGTH = {self._summary_max_length};
                const MAX_TEXT_LENGTH = {self._max_text_length};
                
                const excludeSelectors = [
                    'script', 'style', 'noscript', 'svg', 'iframe',
                    '.ad', '.advertisement', '.ads', '.ad-container',
                    '.recommend', '.feed', '.sidebar', '.side-bar',
                    '#content_right', '.footer', '.modal', '.popup',
                    '[aria-hidden="true"]', '.hidden', '.hide',
                    '.breadcrumb', '.pagination', '.social-share'
                ];
                
                const isExcluded = (el) => {{
                    if (!el) return true;
                    for (const selector of excludeSelectors) {{
                        try {{
                            if (el.closest(selector)) return true;
                        }} catch(e) {{}}
                        try {{
                            if (el.matches && el.matches(selector)) return true;
                        }} catch(e) {{}}
                    }}
                    return false;
                }};
                
                const isVisible = (el) => {{
                    if (!el) return false;
                    if (!PRIORITIZE_VISIBLE) return true;
                    try {{
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) return false;
                        const style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden') return false;
                        if (parseFloat(style.opacity) < 0.1) return false;
                        const viewportHeight = window.innerHeight;
                        if (rect.top > viewportHeight || rect.bottom < 0) return false;
                        return true;
                    }} catch(e) {{
                        return false;
                    }}
                }};
                
                const getElementText = (el) => {{
                    if (!el) return '';
                    let text = '';
                    try {{
                        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {{
                            text = el.value || el.placeholder || '';
                        }} else {{
                            text = el.innerText || el.textContent || '';
                        }}
                    }} catch(e) {{
                        text = '';
                    }}
                    return text.substring(0, MAX_TEXT_LENGTH).replace(/\\s+/g, ' ').trim();
                }};
                
                const addElement = (el, priority) => {{
                    if (!el) return;
                    if (results.length >= MAX_ELEMENTS) return;
                    if (isExcluded(el)) return;
                    if (!isVisible(el)) return;
                    
                    const text = getElementText(el);
                    const id = el.id || '';
                    const className = (el.className || '').toString().substring(0, 20);
                    const key = (el.tagName || '') + text + id + className;
                    
                    if (!seen.has(key)) {{
                        seen.add(key);
                        
                        let typeInfo = '[元素]';
                        const tag = (el.tagName || '').toLowerCase();
                        const type = el.type || '';
                        
                        if (tag === 'input' || tag === 'textarea') {{
                            typeInfo = '[输入]';
                        }} else if (tag === 'button' || type === 'submit' || type === 'button') {{
                            typeInfo = '[按钮]';
                        }} else if (tag === 'select') {{
                            typeInfo = '[选择]';
                        }} else if (tag === 'a') {{
                            typeInfo = '[链接]';
                        }} else if (el.getAttribute('onclick') || el.getAttribute('role') === 'button') {{
                            typeInfo = '[可点]';
                        }}
                        
                        results.push({{
                            index: results.length,
                            text: text || '(空)',
                            tag: tag,
                            type: type,
                            typeInfo: typeInfo,
                            priority: priority
                        }});
                    }}
                }};
                
                const selectors = {selectors_js};
                selectors.forEach(([selector, priority]) => {{
                    try {{
                        const elements = document.querySelectorAll(selector);
                        elements.forEach(el => addElement(el, priority));
                    }} catch(e) {{}}
                }});
                
                results.sort((a, b) => a.priority - b.priority);
                results.forEach((el, idx) => el.index = idx);
                
                const elements = results.map(el => {{
                    return '[' + el.index + '] ' + el.typeInfo + ' ' + el.text;
                }});
                
                let bodyText = '';
                if (INCLUDE_SUMMARY) {{
                    try {{
                        const clone = document.body ? document.body.cloneNode(true) : null;
                        if (clone) {{
                            excludeSelectors.forEach(selector => {{
                                try {{
                                    clone.querySelectorAll(selector).forEach(el => el.remove());
                                }} catch(e) {{}}
                            }});
                            bodyText = (clone.innerText || clone.textContent || '').substring(0, SUMMARY_MAX_LENGTH).replace(/\\s+/g, ' ').trim();
                        }}
                    }} catch(e) {{
                        try {{
                            bodyText = (document.body && document.body.innerText ? document.body.innerText : '').substring(0, SUMMARY_MAX_LENGTH);
                        }} catch(e2) {{
                            bodyText = '';
                        }}
                    }}
                }}
                
                return JSON.stringify({{
                    elements: elements,
                    bodyText: bodyText,
                    total_inputs: document.querySelectorAll('input, textarea').length,
                    total_buttons: document.querySelectorAll('button, [role="button"]').length,
                    total_links: document.querySelectorAll('a[href]').length
                }});
            }}
        """
    
    async def switch_tab(self, tab_index: int) -> Dict[str, Any]:
        """
        切换标签页
        
        参数:
            tab_index: 标签页索引（从 0 开始）
            
        返回:
            操作结果字典
        """
        await self._ensure_browser_started()
        
        if not self._browser:
            return {"status": "error", "message": "浏览器未初始化"}
        
        try:
            logger.info(f"{Fore.CYAN}[Browser] 正在切换到标签页 [{tab_index}]{Style.RESET_ALL}")
            
            from browser_use.browser.events import SwitchTabEvent
            
            target_id = None
            
            try:
                cdp = self._browser.cdp_client
                if cdp:
                    targets_result = await cdp.send.Target.getTargets()
                    cdp_targets = [t for t in targets_result.get('targetInfos', []) if t.get('type') in ('page', 'tab')]
                    
                    if tab_index >= 0 and tab_index < len(cdp_targets):
                        target_id = cdp_targets[tab_index].get('targetId')
            except Exception:
                pass
            
            if not target_id:
                page_targets = self._browser.session_manager.get_all_page_targets() if self._browser.session_manager else []
                
                if tab_index < 0 or tab_index >= len(page_targets):
                    return {
                        "status": "error",
                        "message": f"标签页索引 {tab_index} 超出范围"
                    }
                
                target_id = page_targets[tab_index].target_id
            
            await self._browser.event_bus.dispatch(SwitchTabEvent(target_id=target_id))
            
            await asyncio.sleep(0.2)
            
            url = await self._browser.get_current_page_url()
            title = await self._browser.get_current_page_title()
            
            logger.info(f"{Fore.GREEN}[Browser] 已切换到标签页: {title}{Style.RESET_ALL}")
            
            return {
                "status": "success",
                "message": f"已切换到标签页 [{tab_index}]",
                "url": url,
                "title": title
            }
            
        except Exception as e:
            error_msg = f"切换标签页失败: {str(e)}"
            logger.error(f"{Fore.RED}[Browser] {error_msg}{Style.RESET_ALL}")
            return {
                "status": "error",
                "message": error_msg
            }
    
    async def close_tab(self) -> Dict[str, Any]:
        """
        关闭当前标签页
        
        返回:
            操作结果字典
        """
        await self._ensure_browser_started()
        
        if not self._browser:
            return {"status": "error", "message": "浏览器未初始化"}
        
        try:
            logger.info(f"{Fore.CYAN}[Browser] 正在关闭当前标签页...{Style.RESET_ALL}")
            
            from browser_use.browser.events import CloseTabEvent
            
            page_targets = self._browser.session_manager.get_all_page_targets() if self._browser.session_manager else []
            
            if len(page_targets) <= 1:
                return {
                    "status": "error",
                    "message": "只剩一个标签页，无法关闭"
                }
            
            focused_target = self._browser.session_manager.get_focused_target() if self._browser.session_manager else None
            if not focused_target:
                return {"status": "error", "message": "无法获取当前标签页"}
            
            target_id = focused_target.target_id
            
            await self._browser.event_bus.dispatch(CloseTabEvent(target_id=target_id))
            
            logger.info(f"{Fore.GREEN}[Browser] 标签页已关闭{Style.RESET_ALL}")
            
            return {
                "status": "success",
                "message": "标签页已关闭"
            }
            
        except Exception as e:
            error_msg = f"关闭标签页失败: {str(e)}"
            logger.error(f"{Fore.RED}[Browser] {error_msg}{Style.RESET_ALL}")
            return {
                "status": "error",
                "message": error_msg
            }
    
    async def list_tabs(self) -> Dict[str, Any]:
        """
        列出所有标签页
        
        返回:
            操作结果字典，包含标签页列表
        """
        await self._ensure_browser_started()
        
        if not self._browser:
            return {"status": "error", "message": "浏览器未初始化"}
        
        try:
            logger.info(f"{Fore.CYAN}[Browser] 正在获取标签页列表...{Style.RESET_ALL}")
            
            tabs_info = []
            
            try:
                cdp = self._browser.cdp_client
                if cdp:
                    targets_result = await cdp.send.Target.getTargets()
                    cdp_targets = targets_result.get('targetInfos', [])
                    
                    for t in cdp_targets:
                        if t.get('type') in ('page', 'tab'):
                            tabs_info.append({
                                "index": len(tabs_info),
                                "url": t.get('url', 'unknown'),
                                "title": t.get('title', 'unknown'),
                                "target_id": t.get('targetId', '')
                            })
                    
                    logger.info(f"{Fore.GREEN}[Browser] CDP 获取到 {len(tabs_info)} 个标签页{Style.RESET_ALL}")
            except Exception as e:
                logger.warning(f"{Fore.YELLOW}[Browser] CDP 查询失败: {e}，尝试 session_manager{Style.RESET_ALL}")
                
                page_targets = self._browser.session_manager.get_all_page_targets() if self._browser.session_manager else []
                
                for i, target in enumerate(page_targets):
                    try:
                        url = target.url if hasattr(target, 'url') else "unknown"
                        title = target.title if hasattr(target, 'title') else "unknown"
                        tabs_info.append({
                            "index": i,
                            "url": url,
                            "title": title
                        })
                    except Exception as ex:
                        logger.warning(f"{Fore.YELLOW}[Browser] 获取标签页 {i} 信息失败: {ex}{Style.RESET_ALL}")
                        tabs_info.append({
                            "index": i,
                            "url": "unknown",
                            "title": "unknown"
                        })
            
            logger.info(f"{Fore.GREEN}[Browser] 标签页列表获取成功，共 {len(tabs_info)} 个{Style.RESET_ALL}")
            
            return {
                "status": "success",
                "message": f"共 {len(tabs_info)} 个标签页",
                "tabs": tabs_info,
                "count": len(tabs_info)
            }
            
        except Exception as e:
            error_msg = f"获取标签页列表失败: {str(e)}"
            logger.error(f"{Fore.RED}[Browser] {error_msg}{Style.RESET_ALL}")
            return {
                "status": "error",
                "message": error_msg
            }
