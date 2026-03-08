"""
浏览器自动化 - 处理 JavaScript 渲染的页面
增强版：添加隐身功能（指纹伪装、反检测）
灵感来自 Scrapling 的 StealthyFetcher 和 playwright-search-mcp
"""
import asyncio
import random
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from datetime import datetime
import logging

from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from config import browser_config, BrowserConfig, StealthConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class EngineState:
    """每个搜索引擎的独立状态"""
    fingerprint: Optional[Dict[str, Any]] = None
    proxy: Optional[str] = None
    user_agent: Optional[str] = None
    viewport: Optional[Dict[str, int]] = None
    timezone: Optional[str] = None
    locale: Optional[str] = None
    last_used: Optional[str] = None


@dataclass
class SavedState:
    """保存的状态 - 包含所有引擎的状态"""
    engines: Dict[str, EngineState] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engines": {
                k: asdict(v) if hasattr(v, "__dataclass_fields__") else v
                for k, v in self.engines.items()
            }
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SavedState":
        state = cls()
        engines_data = data.get("engines", {})
        for engine_id, engine_data in engines_data.items():
            state.engines[engine_id] = EngineState(**engine_data)
        return state


@dataclass
class FingerprintConfig:
    """指纹配置"""
    device_name: str = ""
    locale: str = "zh-CN"
    timezone_id: str = "Asia/Shanghai"
    color_scheme: str = "light"
    reduced_motion: str = "no-preference"
    forced_colors: str = "none"
    viewport: Optional[Dict[str, int]] = None
    user_agent: Optional[str] = None


class BaseBrowserManager:
    """
    浏览器管理器基类 - 提供通用的浏览器管理和状态持久化功能
    灵感来自 playwright-search-mcp 的 BaseBrowserManager
    """

    def __init__(
        self,
        config: Optional[BrowserConfig] = None,
        state_dir: Optional[str] = None,
    ):
        self.config = config or browser_config
        self.stealth_config = self.config.stealth_config if hasattr(self.config, 'stealth_config') else StealthConfig()

        # 状态目录管理
        self._state_dir = self._init_state_dir(state_dir)
        self._fingerprint_file = Path(self._state_dir) / "browser-state-fingerprint.json"

        # 状态缓存
        self._saved_state: Optional[SavedState] = None
        self._device_cache: Optional[Dict[str, DeviceDescriptor]] = None

    def _init_state_dir(self, state_dir: Optional[str]) -> str:
        """初始化状态目录"""
        if state_dir:
            return state_dir

        # 优先使用本地目录
        local_dir = Path.cwd() / ".web-rooter"
        if local_dir.exists():
            return str(local_dir)

        # 否则使用用户主目录
        home_dir = Path.home() / ".web-rooter"
        home_dir.mkdir(parents=True, exist_ok=True)
        return str(home_dir)

    def get_state_dir(self) -> str:
        """获取状态目录"""
        return self._state_dir

    def load_engine_state(self, engine_id: str) -> EngineState:
        """加载指定引擎的状态"""
        state = self._load_fingerprint_from_file()
        return state.engines.get(engine_id, EngineState())

    def save_engine_state(
        self,
        engine_id: str,
        engine_state: EngineState,
        no_save: bool = False,
    ) -> None:
        """保存引擎状态"""
        if no_save:
            return

        try:
            # 加载现有状态
            current_state = self._load_fingerprint_from_file()

            # 更新引擎状态
            engine_state.last_used = datetime.now().isoformat()
            current_state.engines[engine_id] = engine_state

            # 保存到文件
            with open(self._fingerprint_file, "w", encoding="utf-8") as f:
                json.dump(current_state.to_dict(), f, indent=2, ensure_ascii=False)

            logger.info(f"已为引擎 '{engine_id}' 保存浏览器状态")

        except Exception as e:
            logger.error(f"保存浏览器状态失败 for engine '{engine_id}': {e}")

    def _load_fingerprint_from_file(self) -> SavedState:
        """从文件加载指纹状态"""
        saved_state = SavedState()

        if self._fingerprint_file.exists():
            try:
                with open(self._fingerprint_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                saved_state = SavedState.from_dict(data)
                logger.info("已加载所有引擎的浏览器指纹和代理配置")
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"无法加载指纹配置文件，将创建新的：{e}")
        else:
            logger.info("指纹配置文件不存在，将创建新的")

        return saved_state

    @staticmethod
    def get_random_device() -> tuple[str, Dict[str, Any]]:
        """获取随机设备配置"""
        # 使用预定义的设备列表（Playwright Python API 不直接暴露 devices）
        desktop_devices: List[Dict[str, Any]] = [
            {
                "name": "Desktop Chrome",
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "viewport": {"width": 1920, "height": 1080},
                "deviceScaleFactor": 1,
                "isMobile": False,
                "hasTouch": False,
            },
            {
                "name": "Desktop Firefox",
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
                "viewport": {"width": 1920, "height": 1080},
                "deviceScaleFactor": 1,
                "isMobile": False,
                "hasTouch": False,
            },
            {
                "name": "Desktop Safari",
                "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "viewport": {"width": 1920, "height": 1080},
                "deviceScaleFactor": 1,
                "isMobile": False,
                "hasTouch": False,
            },
            {
                "name": "Desktop Linux",
                "userAgent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "viewport": {"width": 1920, "height": 1080},
                "deviceScaleFactor": 1,
                "isMobile": False,
                "hasTouch": False,
            },
        ]

        device = random.choice(desktop_devices)
        # 强制设置 720p 分辨率
        device["viewport"] = {"width": 1280, "height": 720}

        return device["name"], device

    @staticmethod
    def get_random_timezone() -> str:
        """获取随机时区"""
        timezone_list = [
            "Asia/Shanghai",
            "Asia/Tokyo",
            "Asia/Hong_Kong",
            "Asia/Singapore",
            "America/New_York",
            "America/Los_Angeles",
            "Europe/London",
            "Europe/Paris",
        ]
        return random.choice(timezone_list)

    @staticmethod
    def get_random_locale() -> str:
        """获取随机语言"""
        locale_list = ["zh-CN", "zh-HK", "zh-TW", "en-US", "en-GB", "ja-JP", "ko-KR"]
        return random.choice(locale_list)

    def get_host_machine_config(self, user_locale: Optional[str] = None) -> FingerprintConfig:
        """获取宿主机器的配置"""
        locale = user_locale or self.get_random_locale()
        timezone = self.get_random_timezone()
        device_name, device = self.get_random_device()

        hour = datetime.now().hour
        color_scheme = "dark" if hour >= 18 or hour <= 6 else "light"

        return FingerprintConfig(
            device_name=device_name,
            locale=locale,
            timezone_id=timezone,
            color_scheme=color_scheme,
            reduced_motion="no-preference",
            forced_colors="none",
            viewport=device.get("viewport"),
            user_agent=device.get("userAgent"),
        )

    @staticmethod
    def coerce_headless(value: Any) -> bool:
        """规范化 headless 配置"""
        if value is False:
            return False
        if isinstance(value, str):
            v = value.lower()
            if v in ("false", "0", "no"):
                return False
        return True

    @staticmethod
    def get_random_delay(min_ms: int, max_ms: int) -> int:
        """获取随机延迟时间"""
        return random.randint(min_ms, max_ms)

    @staticmethod
    def parse_proxy_config(proxy_url: str) -> Dict[str, Any]:
        """解析代理配置"""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(proxy_url)
            server = f"{parsed.scheme}://{parsed.hostname}"
            if parsed.port:
                server += f":{parsed.port}"

            result = {"server": server}
            if parsed.username:
                from urllib.parse import unquote
                result["username"] = unquote(parsed.username)
            if parsed.password:
                from urllib.parse import unquote
                result["password"] = unquote(parsed.password)

            return result
        except Exception as e:
            logger.warning(f"代理 URL 解析失败 {proxy_url}: {e}")
            return {"server": proxy_url}

    async def create_browser_context(
        self,
        browser: Browser,
        engine_state: Optional[EngineState] = None,
        headless: bool = True,
    ) -> BrowserContext:
        """创建浏览器上下文（子类可重写）"""
        raise NotImplementedError("子类必须实现 create_browser_context 方法")


@dataclass
class BrowserResult:
    """浏览器渲染结果"""
    url: str
    html: str
    title: str
    screenshot: Optional[bytes] = None
    console_logs: List[str] = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.console_logs is None:
            self.console_logs = []


@dataclass
class SearchResult:
    """搜索结果"""
    query: str
    engine: str
    url: str
    html: str
    title: str
    results: List[Dict[str, str]] = field(default_factory=list)
    total_results: int = 0
    search_time: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "engine": self.engine,
            "url": self.url,
            "title": self.title,
            "results": self.results,
            "total_results": self.total_results,
            "search_time": self.search_time,
        }


@dataclass
class SearchEngineResult:
    """单个搜索引擎的结果"""
    engine_id: str
    engine_name: str
    results: List[Dict[str, str]]
    total_results: int
    search_time: float
    error: Optional[str] = None


class UserAgentGenerator:
    """User-Agent 生成器"""

    CHROME_VERSIONS = [
        "120.0.0.0",
        "121.0.0.0",
        "122.0.0.0",
        "123.0.0.0",
    ]

    PLATFORMS = [
        ("Windows NT 10.0; Win64; x64", "Windows"),
        ("Macintosh; Intel Mac OS X 10_15_7", "macOS"),
        ("X11; Linux x86_64", "Linux"),
        ("X11; Ubuntu; Linux x86_64", "Ubuntu"),
    ]

    @classmethod
    def generate(cls) -> str:
        """生成随机 User-Agent"""
        platform, os_name = random.choice(cls.PLATFORMS)
        chrome_version = random.choice(cls.CHROME_VERSIONS)
        return (
            f"Mozilla/5.0 ({platform}) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{chrome_version} Safari/537.36"
        )

    @classmethod
    def get_platform_info(cls) -> Dict[str, str]:
        """获取平台信息"""
        platform, os_name = random.choice(cls.PLATFORMS)
        return {
            "platform": os_name,
            "platform_version": "10.0" if "Windows" in platform else "10_15_7" if "Mac" in platform else "",
        }


class FingerprintGenerator:
    """指纹生成器 - 生成真实的浏览器指纹"""

    @staticmethod
    def generate_canvas_noise() -> str:
        """生成 canvas 指纹噪声的随机种子"""
        return f"{random.random():.10f}"

    @staticmethod
    def get_screen_dims() -> Dict[str, Any]:
        """获取屏幕尺寸"""
        widths = [1920, 1366, 1536, 1440, 2560, 1280]
        heights = [1080, 768, 864, 900, 1440, 720]
        width = random.choice(widths)
        height = random.choice(heights)
        return {
            "width": width,
            "height": height,
            "availWidth": width,
            "availHeight": height - random.randint(30, 100),  # 减去任务栏
            "colorDepth": 24,
            "pixelDepth": 24,
        }

    @staticmethod
    def get_timezone() -> str:
        """获取随机时区"""
        timezones = [
            "Asia/Shanghai",
            "Asia/Tokyo",
            "America/New_York",
            "America/Los_Angeles",
            "Europe/London",
            "Europe/Paris",
        ]
        return random.choice(timezones)

    @staticmethod
    def get_languages() -> List[str]:
        """获取语言列表"""
        language_sets = [
            ["zh-CN", "zh", "en"],
            ["en-US", "en"],
            ["ja-JP", "ja", "en"],
            ["ko-KR", "ko", "en"],
        ]
        return random.choice(language_sets)


class StealthInjector:
    """隐身脚本注入器"""

    # 要注入的 JavaScript 脚本
    STEALTH_SCRIPTS = {
        "chrome_app": """
            if (!window.chrome) {
                window.chrome = {};
            }
            if (!window.chrome.app) {
                window.chrome.app = {};
            }
            if (!window.chrome.app.isInstalled) {
                window.chrome.app.isInstalled = false;
            }
        """,
        "chrome_runtime": """
            if (!window.chrome.runtime) {
                window.chrome.runtime = {};
            }
        """,
        "navigator_fix": """
            Object.defineProperties(navigator, {
                webdriver: { value: false },
                plugins: { value: [] },
                languages: { value: {{languages}} },
            });
        """,
        "canvas_noise": """
            const originalToBlob = HTMLCanvasElement.prototype.toBlob;
            const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
            const noise = {{noise}};

            HTMLCanvasElement.prototype.toBlob = function(...args) {
                // 添加微小噪声
                return originalToBlob.apply(this, args);
            };

            HTMLCanvasElement.prototype.toDataURL = function(...args) {
                return originalToDataURL.apply(this, args);
            };
        """,
        "webgl_vendor": """
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(param) {
                if (param === 37445) {
                    return 'Intel Inc.';
                }
                if (param === 37446) {
                    return 'Intel Iris OpenGL Engine';
                }
                return getParameter.call(this, param);
            };
        """,
        "permissions": """
            if (!navigator.permissions) {
                navigator.permissions = {};
            }
            const originalQuery = navigator.permissions.query;
            navigator.permissions.query = async (parameters) => {
                const result = await originalQuery.call(navigator.permissions, parameters);
                result.state = result.state || 'prompt';
                return result;
            };
        """,
    }

    @classmethod
    def get_init_scripts(cls, config: StealthConfig) -> List[str]:
        """获取要注入的初始化脚本"""
        scripts = []

        scripts.append(cls.STEALTH_SCRIPTS["chrome_app"])
        scripts.append(cls.STEALTH_SCRIPTS["chrome_runtime"])

        languages = FingerprintGenerator.get_languages()
        navigator_fix = cls.STEALTH_SCRIPTS["navigator_fix"].replace(
            "{{languages}}", json.dumps(languages)
        )
        scripts.append(navigator_fix)

        if config.CANVAS_NOISE:
            noise = FingerprintGenerator.generate_canvas_noise()
            canvas_script = cls.STEALTH_SCRIPTS["canvas_noise"].replace("{{noise}}", str(noise))
            scripts.append(canvas_script)

        scripts.append(cls.STEALTH_SCRIPTS["webgl_vendor"])
        scripts.append(cls.STEALTH_SCRIPTS["permissions"])

        return scripts


class AntiBotActions:
    """
    反检测行为模拟器
    灵感来自 playwright-search-mcp 的 anti-bot measures
    """

    def __init__(self, page: Page):
        self.page = page

    async def random_mouse_move(self) -> None:
        """随机鼠标移动"""
        await self.page.mouse.move(
            random.randint(0, 800),
            random.randint(0, 600),
        )

    async def random_scroll(self) -> None:
        """随机滚动"""
        await self.page.evaluate("""
            () => {
                window.scrollTo(0, Math.random() * 500);
            }
        """)

    async def random_delay(self, min_ms: int = 1500, max_ms: int = 3500) -> None:
        """随机延迟"""
        delay = random.randint(min_ms, max_ms)
        await asyncio.sleep(delay / 1000)

    async def perform_anti_detection(self) -> None:
        """执行反检测措施"""
        # 随机鼠标移动
        await self.random_mouse_move()

        # 随机滚动
        await self.random_scroll()

        # 短暂等待
        await self.random_delay()

    async def check_for_captcha(
        self,
        detectors: List[str],
        timeout: int = 1000,
    ) -> bool:
        """检查是否有验证码"""
        for selector in detectors:
            try:
                count = await self.page.locator(selector).count()
                if count > 0:
                    element = self.page.locator(selector).first()
                    is_visible = await element.is_visible(timeout=timeout)
                    if is_visible:
                        logger.warning(f"检测到反爬虫机制！匹配选择器：{selector}")
                        return True
            except Exception as e:
                logger.debug(f"检查选择器 {selector} 失败：{e}")
        return False

    async def handle_captcha(self, error_message: str) -> None:
        """处理验证码（暂停等待用户手动处理）"""
        logger.warning(error_message)
        # 暂停等待用户手动处理
        await asyncio.sleep(120)  # 等待 2 分钟


class BrowserManager(BaseBrowserManager):
    """
    浏览器管理器 - 使用 Playwright（带隐身功能）
    继承自 BaseBrowserManager，提供状态管理和反检测功能

    支持：
    - 普通 Chromium 启动
    - CDP 端点连接
    - 真实 Chrome 浏览器（使用用户已安装的 Chrome）
    """

    def __init__(
        self,
        config: Optional[BrowserConfig] = None,
        stealth_config: Optional[StealthConfig] = None,
        state_dir: Optional[str] = None,
        cdp_url: Optional[str] = None,
        use_real_chrome: bool = False,
        chrome_path: Optional[str] = None,
        user_data_dir: Optional[str] = None,
    ):
        super().__init__(config, state_dir)
        self.stealth_config = stealth_config or self.config.stealth_config

        # CDP 和真实 Chrome 配置
        self.cdp_url = cdp_url or self.config.CDP_URL
        self.use_real_chrome = use_real_chrome or self.config.USE_REAL_CHROME
        self.chrome_path = chrome_path or self.config.CHROME_PATH
        self.user_data_dir = user_data_dir or self.config.USER_DATA_DIR

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._use_stealth = self.stealth_config.ENABLE_STEALTH

    async def start(self, engine_id: str = "default"):
        """启动浏览器（支持普通启动、CDP 连接、真实 Chrome）"""
        self._playwright = await async_playwright().start()

        # 加载引擎状态
        engine_state = self.load_engine_state(engine_id)

        # CDP 连接优先
        if self.cdp_url:
            return await self._start_with_cdp(engine_id)

        # 真实 Chrome 模式
        if self.use_real_chrome:
            return await self._start_with_real_chrome(engine_id)

        # 普通 Chromium 启动
        return await self._start_standard(engine_id, engine_state)

    async def _start_with_cdp(self, engine_id: str):
        """通过 CDP 端点连接浏览器"""
        if not self.cdp_url:
            raise ValueError("CDP URL is required")

        logger.info(f"Connecting to CDP endpoint: {self.cdp_url}")

        # 生成随机 User-Agent
        user_agent = UserAgentGenerator.generate() if self.stealth_config.RANDOM_USER_AGENT else None

        # 生成随机视口
        viewport = random.choice(self.stealth_config.VIEWPORTS) if self.stealth_config.RANDOM_VIEWPORT else {"width": 1920, "height": 1080}

        # 时区和语言
        timezone = self.get_random_timezone()
        locale = self.get_random_locale()

        # 通过 CDP 连接
        self._browser = await self._playwright.chromium.connect_over_cdp(self.cdp_url)

        # 创建上下文
        context_options = {
            "viewport": viewport,
            "user_agent": user_agent,
            "locale": locale,
            "timezone_id": timezone,
            "device_scale_factor": 1,
            "is_mobile": False,
            "has_touch": False,
        }

        # 代理支持
        if engine_state.proxy:
            proxy_config = self.parse_proxy_config(engine_state.proxy)
            context_options["proxy"] = proxy_config
            logger.info(f"使用代理：{engine_state.proxy}")

        self._context = await self._browser.new_context(**context_options)

        # 拦截资源
        if self.stealth_config.BLOCK_RESOURCES:
            await self._context.route("**/*", self._stealth_route_handler)

        # 注入隐身脚本
        if self._use_stealth:
            await self._inject_stealth_scripts()

        logger.info(f"Connected to CDP endpoint: {self.cdp_url}")

    async def _start_with_real_chrome(self, engine_id: str):
        """启动真实 Chrome 浏览器"""
        logger.info("Starting real Chrome browser")

        # 检测 Chrome 安装路径
        chrome_executable = self._detect_chrome_path()

        # 用户数据目录
        user_data = self.user_data_dir or str(Path.home() / ".web-rooter" / "chrome-user-data")
        Path(user_data).mkdir(parents=True, exist_ok=True)

        logger.info(f"Chrome executable: {chrome_executable}")
        logger.info(f"User data dir: {user_data}")

        # 生成随机 User-Agent
        user_agent = UserAgentGenerator.generate() if self.stealth_config.RANDOM_USER_AGENT else None

        # 生成随机视口
        viewport = random.choice(self.stealth_config.VIEWPORTS) if self.stealth_config.RANDOM_VIEWPORT else {"width": 1920, "height": 1080}

        # 时区和语言
        timezone = self.get_random_timezone()
        locale = self.get_random_locale()

        # 浏览器启动参数
        browser_args = [
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            f"--user-data-dir={user_data}",
        ]

        # 添加额外参数
        if self.stealth_config.DISABLE_WEBRTC:
            browser_args.append("--disable-webrtc")

        if self.stealth_config.RANDOM_USER_AGENT and user_agent:
            browser_args.append(f"--user-agent={user_agent}")

        # 启动浏览器
        self._browser = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=user_data,
            executable_path=chrome_executable,
            headless=self.config.HEADLESS,
            args=browser_args,
            viewport=viewport,
            user_agent=user_agent,
            locale=locale,
            timezone_id=timezone,
            device_scale_factor=1,
            is_mobile=False,
            has_touch=False,
        )

        # 持久化上下文直接返回 context
        self._context = self._browser

        logger.info("Real Chrome browser started with persistent context")

    async def _start_standard(self, engine_id: str, engine_state: EngineState):
        """标准 Chromium 启动"""
        # 生成随机 User-Agent
        if self.stealth_config.RANDOM_USER_AGENT:
            user_agent = UserAgentGenerator.generate()
        elif engine_state.user_agent:
            user_agent = engine_state.user_agent
        else:
            user_agent = self.config.USER_AGENT if hasattr(self.config, 'USER_AGENT') else (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "Chrome/120.0.0.0 Safari/537.36"
            )

        # 生成随机视口
        if self.stealth_config.RANDOM_VIEWPORT:
            viewport = random.choice(self.stealth_config.VIEWPORTS)
        elif engine_state.viewport:
            viewport = engine_state.viewport
        else:
            viewport = {"width": 1920, "height": 1080}

        # 时区和语言
        timezone = (
            engine_state.timezone or
            self.stealth_config.TIMEZONE or
            self.get_random_timezone()
        )
        locale = (
            engine_state.locale or
            self.stealth_config.ACCEPT_LANGUAGE or
            self.get_random_locale()
        )

        # 浏览器启动参数
        browser_args = [
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
        ]

        # 添加额外参数
        if self.stealth_config.DISABLE_WEBRTC:
            browser_args.append("--disable-webrtc")

        # 启动浏览器
        self._browser = await self._playwright.chromium.launch(
            headless=self.config.HEADLESS,
            args=browser_args,
        )

        # 创建上下文
        context_options = {
            "viewport": viewport,
            "user_agent": user_agent,
            "locale": locale,
            "timezone_id": timezone,
            "device_scale_factor": 1,
            "is_mobile": False,
            "has_touch": False,
        }

        # 权限控制
        if self.stealth_config.DISABLE_WEBRTC:
            context_options["permissions"] = []

        # 代理支持
        if engine_state.proxy:
            proxy_config = self.parse_proxy_config(engine_state.proxy)
            context_options["proxy"] = proxy_config
            logger.info(f"使用代理：{engine_state.proxy}")

        self._context = await self._browser.new_context(**context_options)

        # 拦截资源
        if self.stealth_config.BLOCK_RESOURCES:
            await self._context.route("**/*", self._stealth_route_handler)

        # 注入隐身脚本
        if self._use_stealth:
            await self._inject_stealth_scripts()

        logger.info(f"Browser started with stealth mode: {self._use_stealth}")

        # 保存引擎状态
        self.save_engine_state(engine_id, EngineState(
            fingerprint={
                "user_agent": user_agent,
                "viewport": viewport,
                "timezone": timezone,
                "locale": locale,
            },
            proxy=engine_state.proxy,
            user_agent=user_agent,
            viewport=viewport,
            timezone=timezone,
            locale=locale,
        ))

    def _detect_chrome_path(self) -> str:
        """检测 Chrome 安装路径"""
        if self.chrome_path:
            return self.chrome_path

        import platform
        import os

        system = platform.system()

        if system == "Windows":
            paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
            ]
        elif system == "Darwin":
            paths = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            ]
        else:  # Linux
            paths = [
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/chromium-browser",
                "/usr/bin/chromium",
            ]

        for path in paths:
            if Path(path).exists():
                return path

        # 默认返回第一个路径（可能会失败）
        return paths[0]

    async def _stealth_route_handler(self, route):
        """隐身资源拦截"""
        resource_type = route.request.resource_type

        # 拦截跟踪脚本
        if self.stealth_config.BLOCK_TRACKERS:
            url = route.request.url
            if any(tracker in url for tracker in [
                "analytics", "tracking", "beacon", "pixel",
                "doubleclick", "googletag", "facebook.net"
            ]):
                await route.abort()
                return

        # 拦截图片和字体
        if self.stealth_config.BLOCK_IMAGES and resource_type == "image":
            await route.abort()
        elif self.stealth_config.BLOCK_FONTS and resource_type == "font":
            await route.abort()
        else:
            await route.continue_()

    async def _inject_stealth_scripts(self):
        """注入隐身脚本"""
        # 在页面创建时注入脚本的钩子
        async def init_page(page: Page):
            scripts = StealthInjector.get_init_scripts(self.stealth_config)
            for script in scripts:
                await page.add_init_script(script)

        self._context.on("page", init_page)

    async def close(self):
        """关闭浏览器"""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser closed")

    async def __aenter__(self) -> "BrowserManager":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def fetch(
        self,
        url: str,
        wait_for: Optional[str] = None,
        wait_for_timeout: int = 5000,
        scroll: bool = False,
        take_screenshot: bool = False,
        javascript: Optional[str] = None,
        handle_cloudflare: bool = True,
        engine_id: Optional[str] = None,
        perform_anti_bot: bool = True,
    ) -> BrowserResult:
        """
        使用浏览器获取页面（支持 JavaScript 和 Cloudflare 处理）

        Args:
            url: 目标 URL
            wait_for: 等待的 CSS 选择器
            wait_for_timeout: 等待超时（毫秒）
            scroll: 是否滚动到底部
            take_screenshot: 是否截图
            javascript: 执行的 JavaScript 代码
            handle_cloudflare: 是否自动处理 Cloudflare 验证
            engine_id: 搜索引擎 ID（用于状态管理）
            perform_anti_bot: 是否执行反检测措施

        Returns:
            BrowserResult: 渲染后的结果
        """
        if not self._browser:
            await self.start(engine_id or "default")

        console_logs = []

        try:
            page = await self._context.new_page()

            # 收集控制台日志
            page.on("console", lambda msg: console_logs.append(msg.text))

            # 设置超时
            page.set_default_timeout(self.config.TIMEOUT)

            # 导航到页面
            await page.goto(url, wait_until="networkidle" if self.config.WAIT_FOR_NETWORK else "domcontentloaded")

            # 执行反检测措施
            if perform_anti_bot:
                anti_bot = AntiBotActions(page)
                await anti_bot.perform_anti_detection()

            # 处理 Cloudflare Turnstile
            if handle_cloudflare and self.stealth_config.AUTO_CLOUDFLARE:
                await self._handle_cloudflare(page, wait_for_timeout)

            # 等待特定元素
            if wait_for:
                try:
                    await page.wait_for_selector(wait_for, timeout=wait_for_timeout)
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout waiting for {wait_for}")

            # 执行自定义 JavaScript
            if javascript:
                await page.evaluate(javascript)

            # 滚动页面
            if scroll:
                await self._scroll_to_bottom(page)

            # 截图
            screenshot = None
            if take_screenshot:
                screenshot = await page.screenshot(full_page=True)

            # 获取内容
            html = await page.content()
            title = await page.title()

            await page.close()

            return BrowserResult(
                url=url,
                html=html,
                title=title,
                screenshot=screenshot,
                console_logs=console_logs,
            )

        except Exception as e:
            logger.exception(f"Error fetching {url}")
            return BrowserResult(
                url=url,
                html="",
                title="",
                error=str(e),
            )

    async def search(
        self,
        query: str,
        engine_id: str = "google",
        engine_config: Optional["EngineConfig"] = None,
        limit: int = 10,
    ) -> "SearchResult":
        """
        执行搜索（使用引擎配置）

        Args:
            query: 搜索查询
            engine_id: 搜索引擎 ID
            engine_config: 引擎配置（从 ConfigLoader 获取）
            limit: 结果数量限制

        Returns:
            SearchResult: 搜索结果
        """
        from core.engine_config import get_engine_config, EngineConfig

        if engine_config is None:
            engine_config = get_engine_config(engine_id)

        if not engine_config:
            raise ValueError(f"未知的搜索引擎：{engine_id}")

        # 构建搜索 URL
        search_url = f"{engine_config.baseUrl}{engine_config.searchPath}{query.replace(' ', '+')}"

        logger.info(f"正在导航到{engine_config.name}搜索页面：{search_url}")

        # 获取引擎状态
        engine_state = self.load_engine_state(engine_id)

        # 获取自定义延迟
        delay_config = engine_config.customDelay or {"min": 1000, "max": 3000}

        # 执行搜索
        result = await self.fetch(
            url=search_url,
            engine_id=engine_id,
            perform_anti_bot=engine_config.antiBot.enabled if engine_config.antiBot else True,
        )

        # 检查反爬虫检测
        if engine_config.antiBot and engine_config.antiBot.enabled:
            anti_bot = AntiBotActions(self._context.pages[0] if self._context.pages else await self._context.new_page())
            detectors = engine_config.antiBot.detectors
            if detectors:
                # 注意：这里需要在页面打开后检查
                pass

        return SearchResult(
            query=query,
            engine=engine_id,
            url=result.url,
            html=result.html,
            title=result.title,
        )

    async def _handle_cloudflare(self, page: Page, timeout: int = 5000):
        """处理 Cloudflare Turnstile 验证"""
        try:
            # 等待 Turnstile 出现
            await page.wait_for_selector("iframe[src*='challenges.cloudflare.com']", timeout=timeout)
            logger.info("Cloudflare challenge detected")

            # 等待验证完成（通常会自动完成）
            await asyncio.sleep(2)

            # 检查是否还在挑战页面
            is_challenged = await page.query_selector("iframe[src*='challenges.cloudflare.com']")
            if is_challenged:
                logger.info("Waiting for Cloudflare challenge to resolve...")
                await asyncio.sleep(3)

        except asyncio.TimeoutError:
            # 没有 Cloudflare 挑战，继续
            pass
        except Exception as e:
            logger.warning(f"Error handling Cloudflare: {e}")

    async def _scroll_to_bottom(self, page: Page):
        """滚动到页面底部"""
        await page.evaluate("""
            () => new Promise((resolve) => {
                let scrollHeight = document.body.scrollHeight;
                let totalHeight = 0;
                let distance = 500;
                let timer = setInterval(() => {
                    window.scrollBy(0, distance);
                    totalHeight += distance;
                    if (totalHeight >= scrollHeight) {
                        clearInterval(timer);
                        resolve();
                    }
                    if (document.body.scrollHeight - window.scrollY - window.innerHeight < 100) {
                        clearInterval(timer);
                        resolve();
                    }
                }, 100);
            })
        """)

    async def click_and_wait(
        self,
        url: str,
        selector: str,
        wait_for_selector: Optional[str] = None,
    ) -> BrowserResult:
        """点击元素并等待"""
        if not self._browser:
            await self.start()

        try:
            page = await self._context.new_page()
            page.set_default_timeout(self.config.TIMEOUT)

            await page.goto(url, wait_until="domcontentloaded")

            # 点击元素
            await page.click(selector)

            # 等待新内容
            if wait_for_selector:
                await page.wait_for_selector(wait_for_selector)
            else:
                await page.wait_for_load_state("networkidle")

            html = await page.content()
            title = await page.title()

            await page.close()

            return BrowserResult(
                url=page.url,
                html=html,
                title=title,
            )

        except Exception as e:
            logger.exception(f"Error in click_and_wait")
            return BrowserResult(
                url=url,
                html="",
                title="",
                error=str(e),
            )

    async def fill_and_submit(
        self,
        url: str,
        form_data: Dict[str, str],
        submit_selector: str = "button[type='submit']",
    ) -> BrowserResult:
        """填写表单并提交"""
        if not self._browser:
            await self.start()

        try:
            page = await self._context.new_page()
            page.set_default_timeout(self.config.TIMEOUT)

            await page.goto(url, wait_until="domcontentloaded")

            # 填写表单
            for selector, value in form_data.items():
                await page.fill(selector, value)

            # 提交
            await page.click(submit_selector)
            await page.wait_for_load_state("networkidle")

            html = await page.content()
            title = await page.title()

            await page.close()

            return BrowserResult(
                url=page.url,
                html=html,
                title=title,
            )

        except Exception as e:
            logger.exception(f"Error in fill_and_submit")
            return BrowserResult(
                url=url,
                html="",
                title="",
                error=str(e),
            )

    async def get_interactive(self, url: str) -> tuple[Page, BrowserResult]:
        """
        获取交互式页面（用于后续操作）
        返回 page 对象，使用完后需要手动关闭
        """
        if not self._browser:
            await self.start()

        page = await self._context.new_page()
        page.set_default_timeout(self.config.TIMEOUT)

        await page.goto(url, wait_until="networkidle")

        result = BrowserResult(
            url=page.url,
            html=await page.content(),
            title=await page.title(),
        )

        return page, result
