"""
浏览器自动化 - 处理 JavaScript 渲染的页面
增强版：添加隐身功能（指纹伪装、反检测）
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

from playwright.async_api import async_playwright, Browser, Page, BrowserContext, TimeoutError as PlaywrightTimeoutError
from config import browser_config, BrowserConfig, StealthConfig
from core.challenge_workflow import get_challenge_workflow_runner
from core.auth_profiles import get_auth_profile_registry
from core.cli_entry import build_cli_command

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
    cookies: Dict[str, str] = None
    metadata: Dict[str, Any] = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.console_logs is None:
            self.console_logs = []
        if self.cookies is None:
            self.cookies = {}
        if self.metadata is None:
            self.metadata = {}


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
    """

    def __init__(self, page: Page):
        self.page = page
        self._challenge_runner = get_challenge_workflow_runner()
        self._challenge_keywords = [
            "captcha",
            "recaptcha",
            "hcaptcha",
            "cloudflare",
            "challenge",
            "verify you are human",
            "unusual traffic",
            "access denied",
            "人机验证",
            "访问受限",
        ]

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
                    element = self.page.locator(selector).first
                    is_visible = await element.is_visible(timeout=timeout)
                    if is_visible:
                        logger.warning(f"检测到反爬虫机制！匹配选择器：{selector}")
                        return True
            except Exception as e:
                logger.debug(f"检查选择器 {selector} 失败：{e}")
        return False

    async def detect_challenge_markers(self) -> bool:
        """通过标题/URL/页面文本检测挑战页。"""
        try:
            title = (await self.page.title()).lower()
        except Exception:
            title = ""

        current_url = (self.page.url or "").lower()

        try:
            body_text = await self.page.evaluate(
                "() => (document.body && document.body.innerText ? document.body.innerText.slice(0, 5000) : '')"
            )
            body_text = (body_text or "").lower()
        except Exception:
            body_text = ""

        merged = f"{title} {current_url} {body_text}"
        return any(keyword in merged for keyword in self._challenge_keywords)

    async def attempt_challenge_bypass(
        self,
        detectors: Optional[List[str]] = None,
        max_attempts: int = 3,
    ) -> bool:
        """
        尝试自动绕过挑战页：
        - 点击页面中可见的验证按钮/checkbox
        - 尝试点击 challenge iframe
        - 尝试操作 reCAPTCHA/hCaptcha frame 内控件
        """
        detectors = list(detectors or [])
        forced_profile = os.getenv("WEB_ROOTER_CHALLENGE_PROFILE", "").strip() or None
        max_profiles = max(1, int(os.getenv("WEB_ROOTER_CHALLENGE_MAX_PROFILES", "3") or 3))

        for attempt in range(max(1, max_attempts)):
            # 先走可编排 workflow，再走旧有硬编码动作，实现平滑兼容。
            try:
                workflow_report = await self._challenge_runner.run(
                    page=self.page,
                    url=self.page.url,
                    detectors=detectors,
                    profile_name=forced_profile,
                    max_rounds=1,
                    max_profiles=max_profiles,
                )
                if workflow_report.get("resolved"):
                    logger.info(
                        "Challenge workflow resolved: profile=%s attempt=%s",
                        workflow_report.get("profile"),
                        attempt + 1,
                    )
                    return True
                if workflow_report.get("errors"):
                    logger.debug(
                        "Challenge workflow errors: %s",
                        "; ".join(workflow_report.get("errors", [])[:2]),
                    )
            except Exception as workflow_exc:
                logger.debug("Challenge workflow execution failed: %s", workflow_exc)

            await self._click_challenge_controls()
            await self.random_delay(900, 1700)

            still_challenged = (
                await self.check_for_captcha(detectors, timeout=600)
                if detectors
                else await self.detect_challenge_markers()
            )
            if not still_challenged:
                return True

            if attempt < max_attempts - 1:
                await self.random_mouse_move()
                await self.random_scroll()
                await self.random_delay(700, 1400)

        return False

    async def _click_challenge_controls(self) -> None:
        """点击常见挑战控件（best-effort）。"""
        click_selectors = [
            "input[type='checkbox'][name*='captcha' i]",
            "input[type='checkbox'][id*='captcha' i]",
            "input[type='checkbox'][name*='cf' i]",
            "input[type='checkbox'][id*='cf' i]",
            "button:has-text('Verify')",
            "button:has-text('Continue')",
            "button:has-text('I am human')",
            "button:has-text('I'm human')",
            "button:has-text('Not a robot')",
            "button:has-text('继续')",
            "button:has-text('验证')",
            "button:has-text('确认')",
            "button:has-text('我是人类')",
            "[role='button']:has-text('Verify')",
            "[role='button']:has-text('Continue')",
            "[role='button']:has-text('继续')",
        ]

        for selector in click_selectors:
            try:
                locator = self.page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible(timeout=400):
                    await locator.click(timeout=1200, force=True)
                    await asyncio.sleep(random.uniform(0.25, 0.8))
            except Exception:
                continue

        # Cloudflare challenge iframe 常见路径：点击 iframe 中心位置
        try:
            iframe = self.page.locator("iframe[src*='challenges.cloudflare.com']").first
            if await iframe.count() > 0 and await iframe.is_visible(timeout=600):
                box = await iframe.bounding_box()
                if box:
                    await self.page.mouse.click(
                        box["x"] + box["width"] / 2,
                        box["y"] + box["height"] / 2,
                    )
                    await asyncio.sleep(random.uniform(0.3, 0.9))
        except Exception:
            pass

        # 尝试在 frame 内点击验证码控件（reCAPTCHA/hCaptcha/Cloudflare Turnstile）
        for frame in self.page.frames:
            frame_url = (frame.url or "").lower()
            if not any(
                token in frame_url
                for token in ("captcha", "recaptcha", "hcaptcha", "challenge", "cloudflare")
            ):
                continue
            for frame_selector in (
                "#recaptcha-anchor",
                "input[type='checkbox']",
                "div[role='checkbox']",
                "button",
            ):
                try:
                    node = frame.locator(frame_selector).first
                    if await node.count() > 0 and await node.is_visible(timeout=500):
                        await node.click(timeout=1200, force=True)
                        await asyncio.sleep(random.uniform(0.3, 0.9))
                        break
                except Exception:
                    continue

    async def handle_captcha(
        self,
        error_message: str,
        detectors: Optional[List[str]] = None,
        wait_seconds: int = 12,
    ) -> bool:
        """处理验证码/挑战页，优先自动尝试，失败后短等待。"""
        logger.warning(error_message)
        resolved = await self.attempt_challenge_bypass(detectors=detectors, max_attempts=3)
        if resolved:
            logger.info("自动挑战页交互成功，继续后续流程")
            return True

        # 最后短等待，给页面自动跳转留时间
        for _ in range(max(1, wait_seconds // 2)):
            await asyncio.sleep(2)
            still_challenged = (
                await self.check_for_captcha(detectors, timeout=600)
                if detectors
                else await self.detect_challenge_markers()
            )
            if not still_challenged:
                return True

        logger.warning("自动挑战页交互未完全解除，继续执行后续兜底流程")
        return False


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
        self._start_lock = asyncio.Lock()
        self._auth_registry = get_auth_profile_registry()
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._active_operations: set[asyncio.Task[Any]] = set()
        self._loop_with_handler: Optional[asyncio.AbstractEventLoop] = None
        self._previous_loop_exception_handler = None

    @staticmethod
    def _is_ignorable_loop_exception(context: Dict[str, Any]) -> bool:
        message = str(context.get("message", "")).lower()
        exc = context.get("exception")
        detail = str(exc).lower() if exc else ""
        merged = f"{message} {detail}"
        if (
            "future exception was never retrieved" in message
            and "timeout" in detail
            and "waiting for locator(" in detail
        ):
            return True
        close_race_markers = [
            "future exception was never retrieved",
            "target closed",
            "target page, context or browser has been closed",
            "err_aborted",
            "frame was detached",
            "navigating to ",
        ]
        marker_hits = sum(1 for marker in close_race_markers if marker in merged)
        return marker_hits >= 2

    def _install_loop_exception_handler(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        if self._loop_with_handler is loop:
            return

        self._loop_with_handler = loop
        self._previous_loop_exception_handler = loop.get_exception_handler()

        def _handler(current_loop: asyncio.AbstractEventLoop, context: Dict[str, Any]) -> None:
            if self._is_ignorable_loop_exception(context):
                logger.debug("Ignore loop close-race exception: %s", context.get("exception") or context.get("message"))
                return
            if self._previous_loop_exception_handler:
                self._previous_loop_exception_handler(current_loop, context)
            else:
                current_loop.default_exception_handler(context)

        loop.set_exception_handler(_handler)

    def _restore_loop_exception_handler(self) -> None:
        loop = self._loop_with_handler
        if not loop:
            return
        try:
            loop.set_exception_handler(self._previous_loop_exception_handler)
        except Exception:
            pass
        self._loop_with_handler = None
        self._previous_loop_exception_handler = None

    def _track_background_task(self, task: asyncio.Task[Any]) -> None:
        """Track async callbacks and swallow close-race exceptions from detached tasks."""
        self._background_tasks.add(task)

        def _on_done(done: asyncio.Task[Any]) -> None:
            self._background_tasks.discard(done)
            if done.cancelled():
                return
            try:
                done.result()
            except Exception as exc:
                msg = str(exc).lower()
                if (
                    "target closed" in msg
                    or "has been closed" in msg
                    or "err_aborted" in msg
                    or "frame was detached" in msg
                ):
                    logger.debug("Ignore background task close race: %s", exc)
                    return
                logger.debug("Background task failed: %s", exc)

        task.add_done_callback(_on_done)

    def _track_active_operation_current_task(self) -> Optional[asyncio.Task[Any]]:
        """Track current coroutine task as an active browser operation."""
        task = asyncio.current_task()
        if task:
            self._active_operations.add(task)
        return task

    def _untrack_active_operation(self, task: Optional[asyncio.Task[Any]]) -> None:
        if task:
            self._active_operations.discard(task)

    @staticmethod
    def _build_local_storage_init_script(local_storage: Dict[str, Dict[str, str]]) -> str:
        payload = json.dumps(local_storage, ensure_ascii=False)
        return (
            "(() => {"
            f"const store = {payload};"
            "const origin = window.location.origin;"
            "const entries = store[origin] || store['*'];"
            "if (!entries) return;"
            "for (const [k, v] of Object.entries(entries)) {"
            "try { window.localStorage.setItem(String(k), String(v)); } catch (_) {}"
            "}"
            "})();"
        )

    async def _apply_auth_profile(self, page: Page, target_url: str) -> Dict[str, Any]:
        """根据 URL 匹配本地登录 profile 并注入上下文。"""
        try:
            payload = self._auth_registry.collect_auth_payload(target_url)
        except Exception as exc:
            logger.debug("collect auth profile failed for %s: %s", target_url, exc)
            return {
                "matched": None,
                "configured": False,
                "warnings": [f"collect_failed:{exc}"],
                "requires_user_input": False,
            }

        headers = payload.pop("headers", {}) if isinstance(payload, dict) else {}
        cookies = payload.pop("cookies", []) if isinstance(payload, dict) else []
        local_storage = payload.pop("local_storage", {}) if isinstance(payload, dict) else {}
        if not isinstance(payload, dict):
            payload = {"matched": None, "configured": False, "warnings": [], "requires_user_input": False}

        applied_headers = 0
        applied_cookies = 0
        applied_local_storage = 0

        if isinstance(headers, dict) and headers:
            try:
                await page.set_extra_http_headers({str(k): str(v) for k, v in headers.items() if str(k).strip()})
                applied_headers = len(headers)
            except Exception as exc:
                payload.setdefault("warnings", []).append(f"apply_headers_failed:{exc}")

        if isinstance(cookies, list) and cookies:
            try:
                await page.context.add_cookies(cookies)
                applied_cookies = len(cookies)
            except Exception as exc:
                payload.setdefault("warnings", []).append(f"apply_cookies_failed:{exc}")

        if isinstance(local_storage, dict) and local_storage:
            try:
                await page.add_init_script(self._build_local_storage_init_script(local_storage))
                applied_local_storage = sum(len(v) for v in local_storage.values() if isinstance(v, dict))
            except Exception as exc:
                payload.setdefault("warnings", []).append(f"apply_local_storage_failed:{exc}")

        payload["applied_headers"] = applied_headers
        payload["applied_cookies"] = applied_cookies
        payload["applied_local_storage_items"] = applied_local_storage
        return payload

    @staticmethod
    def _detect_login_wall(url: str, title: str, html: str) -> bool:
        merged = f"{title or ''}\n{url or ''}\n{(html or '')[:12000]}".lower()
        strong_markers = [
            "sign in to continue",
            "log in to continue",
            "please log in",
            "please sign in",
            "scan qr code to login",
            "login required",
            "登录后查看更多",
            "登录后可见",
            "请先登录",
            "扫码登录",
            "请登录后继续",
        ]
        if any(marker in merged for marker in strong_markers):
            return True

        weak_markers = ["sign in", "log in", "登录", "register", "立即登录", "立即注册", "验证身份"]
        weak_hits = sum(1 for marker in weak_markers if marker in merged)
        return weak_hits >= 3

    async def start(self, engine_id: str = "default"):
        """启动浏览器（支持普通启动、CDP 连接、真实 Chrome）"""
        if self._browser and self._context and self._playwright:
            return

        async with self._start_lock:
            if self._browser and self._context and self._playwright:
                return

            if self._playwright is None:
                self._playwright = await async_playwright().start()
            self._install_loop_exception_handler()

            # 加载引擎状态
            engine_state = self.load_engine_state(engine_id)

            # CDP 连接优先
            if self.cdp_url:
                return await self._start_with_cdp(engine_id)

            # 真实 Chrome 模式
            if self.use_real_chrome:
                return await self._start_with_real_chrome(engine_id)

            # 普通 Chromium 启动
            try:
                return await self._start_standard(engine_id, engine_state)
            except Exception as exc:
                message = str(exc).lower()
                missing_browser = (
                    "executable doesn't exist" in message
                    or "playwright was just installed" in message
                )
                if missing_browser:
                    logger.warning(
                        "Playwright bundled browser missing, fallback to real Chrome: %s",
                        exc,
                    )
                    return await self._start_with_real_chrome(engine_id)
                raise

    async def _start_with_cdp(self, engine_id: str):
        """通过 CDP 端点连接浏览器"""
        if not self.cdp_url:
            raise ValueError("CDP URL is required")

        logger.info(f"Connecting to CDP endpoint: {self.cdp_url}")
        engine_state = self.load_engine_state(engine_id)

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

        def on_page(page: Page) -> None:
            self._track_background_task(asyncio.create_task(init_page(page)))

        self._context.on("page", on_page)

    async def close(self):
        """关闭浏览器"""
        async with self._start_lock:
            current = asyncio.current_task()
            pending_ops = [
                task for task in self._active_operations
                if task is not current and not task.done()
            ]
            if pending_ops:
                done, still_pending = await asyncio.wait(
                    pending_ops,
                    timeout=float(os.getenv("WEB_ROOTER_BROWSER_CLOSE_GRACE_SEC", "2.5")),
                )
                for task in done:
                    try:
                        task.result()
                    except Exception as exc:
                        logger.debug("active operation finished with error during close: %s", exc)
                if still_pending:
                    for task in still_pending:
                        task.cancel()
                    await asyncio.gather(*still_pending, return_exceptions=True)

            if self._background_tasks:
                pending = list(self._background_tasks)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                self._background_tasks.clear()

            if self._context:
                try:
                    pages = list(getattr(self._context, "pages", []) or [])
                    for page in pages:
                        try:
                            if page and not page.is_closed():
                                await page.close()
                        except Exception as exc:
                            logger.debug(f"关闭 page 失败: {exc}")
                except Exception as exc:
                    logger.debug(f"关闭 context pages 失败: {exc}")

            if self._browser:
                try:
                    await self._browser.close()
                except Exception as exc:
                    logger.debug(f"关闭 browser 失败: {exc}")
            self._browser = None
            self._context = None

            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception as exc:
                    logger.debug(f"关闭 playwright 失败: {exc}")
            self._playwright = None
            self._active_operations.clear()
        logger.info("Browser closed")

    async def __aenter__(self) -> "BrowserManager":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _capture_html(self, page: Page) -> tuple[str, int, bool]:
        """Capture a bounded HTML snapshot so very large DOMs do not flood memory."""
        limit = max(10_000, int(getattr(self.config, "MAX_HTML_CHARS", 250000) or 250000))
        try:
            payload = await page.evaluate(
                """
                (maxChars) => {
                    const root = document.documentElement;
                    if (!root) {
                        return { html: "", html_chars: 0, truncated: false };
                    }
                    const html = root.outerHTML || "";
                    const htmlChars = html.length;
                    return {
                        html: htmlChars > maxChars ? html.slice(0, maxChars) : html,
                        html_chars: htmlChars,
                        truncated: htmlChars > maxChars,
                    };
                }
                """,
                limit,
            )
        except Exception:
            html = await page.content()
            html_chars = len(html)
            truncated = html_chars > limit
            return (html[:limit] if truncated else html, html_chars, truncated)

        if not isinstance(payload, dict):
            return "", 0, False

        html = payload.get("html")
        html_chars = payload.get("html_chars")
        truncated = payload.get("truncated")
        return (
            str(html or ""),
            int(html_chars or 0),
            bool(truncated),
        )

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
        if not self._browser or self._context is None:
            await self.start(engine_id or "default")
        if self._context is None:
            return BrowserResult(
                url=url,
                html="",
                title="",
                error="browser_context_unavailable",
            )

        console_logs: List[str] = []
        max_console_logs = max(1, int(getattr(self.config, "MAX_CONSOLE_LOGS", 50) or 50))
        page: Optional[Page] = None
        op_task = self._track_active_operation_current_task()

        try:
            page = await self._context.new_page()
            anti_bot = AntiBotActions(page)
            auth_profile = await self._apply_auth_profile(page, url)

            # 收集控制台日志
            def _remember_console(msg: Any) -> None:
                if len(console_logs) >= max_console_logs:
                    return
                text = getattr(msg, "text", "")
                text = text if len(text) <= 300 else text[:300] + "...[truncated]"
                console_logs.append(text)

            page.on("console", _remember_console)

            # 设置超时
            page.set_default_timeout(self.config.TIMEOUT)

            # 导航到页面。部分站点永远达不到 networkidle，超时后降级到 domcontentloaded。
            wait_until = "networkidle" if self.config.WAIT_FOR_NETWORK else "domcontentloaded"
            try:
                await page.goto(url, wait_until=wait_until)
            except PlaywrightTimeoutError:
                if wait_until == "networkidle":
                    logger.warning("Navigation timeout with networkidle for %s, retry with domcontentloaded", url)
                    await page.goto(url, wait_until="domcontentloaded")
                else:
                    raise

            # 执行反检测措施
            if perform_anti_bot:
                try:
                    await anti_bot.perform_anti_detection()
                except Exception as anti_bot_error:
                    # 反检测动作不应让抓取整体失败（例如页面重定向时 execution context 重建）
                    logger.warning(f"Anti-bot step failed for {url}: {anti_bot_error}")

            # 处理 Cloudflare Turnstile
            if handle_cloudflare and self.stealth_config.AUTO_CLOUDFLARE:
                await self._handle_cloudflare(page, wait_for_timeout)

            # 页面仍像挑战页时，尝试自动交互绕过
            if handle_cloudflare:
                try:
                    if await anti_bot.detect_challenge_markers():
                        await anti_bot.handle_captcha(
                            "检测到挑战页，尝试自动交互绕过",
                            detectors=[],
                            wait_seconds=8,
                        )
                except Exception as challenge_exc:
                    logger.debug(f"Challenge bypass step failed for {url}: {challenge_exc}")

            # 等待特定元素
            if wait_for:
                try:
                    await page.wait_for_selector(wait_for, timeout=wait_for_timeout)
                except PlaywrightTimeoutError:
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
            html, html_chars, html_truncated = await self._capture_html(page)
            title = await page.title()
            cookie_items = await page.context.cookies([page.url])
            cookie_map = {
                str(item.get("name", "")): str(item.get("value", ""))
                for item in cookie_items
                if item.get("name")
            }
            login_wall = self._detect_login_wall(page.url, title, html)
            result_metadata = {
                "auth": auth_profile,
                "login_wall": login_wall,
                "html_chars": html_chars,
                "html_truncated": html_truncated,
            }
            if login_wall and isinstance(auth_profile, dict):
                if auth_profile.get("matched") is None:
                    result_metadata["login_hint"] = (
                        f"页面存在登录门槛且未命中 auth profile。请先执行 `{build_cli_command('auth-template')}` 并配置本地登录态。"
                    )
                elif auth_profile.get("requires_user_input"):
                    result_metadata["login_hint"] = "已命中 auth profile，但登录态未配置完整，需要用户补充本地凭据。"

            return BrowserResult(
                url=page.url,
                html=html,
                title=title,
                screenshot=screenshot,
                console_logs=console_logs,
                cookies=cookie_map,
                metadata=result_metadata,
            )

        except asyncio.CancelledError:
            logger.debug("Fetch cancelled for %s", url)
            return BrowserResult(
                url=url,
                html="",
                title="",
                error="operation_cancelled",
            )
        except Exception as e:
            logger.error("Error fetching %s: %s", url, e)
            return BrowserResult(
                url=url,
                html="",
                title="",
                error=str(e),
            )
        finally:
            if page and not page.is_closed():
                try:
                    await page.close()
                except Exception:
                    pass
            self._untrack_active_operation(op_task)

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
        from core.search.engine_config import get_engine_config, EngineConfig

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
        selector = "iframe[src*='challenges.cloudflare.com']"
        try:
            # Poll query_selector instead of wait_for_selector to avoid detached-frame timeout futures.
            loop = asyncio.get_running_loop()
            deadline = loop.time() + max(1.0, timeout / 1000.0)
            challenged = None
            while loop.time() < deadline:
                challenged = await page.query_selector(selector)
                if challenged:
                    break
                await asyncio.sleep(0.25)

            if not challenged:
                return

            logger.info("Cloudflare challenge detected")
            await asyncio.sleep(2)

            resolve_deadline = loop.time() + 6.0
            while loop.time() < resolve_deadline:
                current = await page.query_selector(selector)
                if not current:
                    return
                await asyncio.sleep(0.5)
            logger.info("Cloudflare challenge not fully resolved within grace window")

        except PlaywrightTimeoutError:
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

        op_task = self._track_active_operation_current_task()
        page: Optional[Page] = None
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

            return BrowserResult(
                url=page.url,
                html=html,
                title=title,
            )

        except Exception as e:
            logger.error("Error in click_and_wait: %s", e)
            return BrowserResult(
                url=url,
                html="",
                title="",
                error=str(e),
            )
        finally:
            if page and not page.is_closed():
                try:
                    await page.close()
                except Exception:
                    pass
            self._untrack_active_operation(op_task)

    async def fill_and_submit(
        self,
        url: str,
        form_data: Dict[str, str],
        submit_selector: str = "button[type='submit']",
    ) -> BrowserResult:
        """填写表单并提交"""
        if not self._browser:
            await self.start()

        op_task = self._track_active_operation_current_task()
        page: Optional[Page] = None
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

            return BrowserResult(
                url=page.url,
                html=html,
                title=title,
            )

        except Exception as e:
            logger.error("Error in fill_and_submit: %s", e)
            return BrowserResult(
                url=url,
                html="",
                title="",
                error=str(e),
            )
        finally:
            if page and not page.is_closed():
                try:
                    await page.close()
                except Exception:
                    pass
            self._untrack_active_operation(op_task)

    async def get_interactive(self, url: str) -> tuple[Page, BrowserResult]:
        """
        获取交互式页面（用于后续操作）
        返回 page 对象，使用完后需要手动关闭
        """
        if not self._browser:
            await self.start()

        op_task = self._track_active_operation_current_task()
        page: Optional[Page] = None
        try:
            page = await self._context.new_page()
            page.set_default_timeout(self.config.TIMEOUT)

            await page.goto(url, wait_until="networkidle")

            result = BrowserResult(
                url=page.url,
                html=await page.content(),
                title=await page.title(),
            )
            return page, result
        except Exception:
            if page and not page.is_closed():
                try:
                    await page.close()
                except Exception:
                    pass
            raise
        finally:
            self._untrack_active_operation(op_task)
