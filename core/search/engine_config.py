"""
搜索引擎配置加载器 - 单例模式

功能:
- 加载 JSON 配置文件
- 合并默认配置和引擎特定配置
- 提供配置访问接口
- 支持配置热重载
"""
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict, fields
import logging

logger = logging.getLogger(__name__)


@dataclass
class AntiBotConfig:
    """反爬虫检测配置"""
    enabled: bool = True
    detectors: List[str] = field(default_factory=list)
    errorMessage: str = "搜索引擎检测到验证机制，需要人工干预。"


@dataclass
class SelectorsConfig:
    """选择器配置"""
    resultContainer: str = "div.result"
    title: str = "h3 a"
    link: str = "a"
    snippet: str = "p"


@dataclass
class EngineConfig:
    """搜索引擎配置"""
    id: str
    name: str
    baseUrl: str
    searchPath: str
    selectors: Dict[str, str]
    headers: Dict[str, str] = field(default_factory=dict)
    antiBot: AntiBotConfig = field(default_factory=AntiBotConfig)
    customDelay: Dict[str, int] = field(default_factory=lambda: {"min": 1000, "max": 3000})
    fallbackSelector: str = 'div:has(a[href*="http"])'
    linkValidation: List[str] = field(default_factory=lambda: ["http"])
    maxResultsPerPage: int = 10
    timezoneList: List[str] = field(default_factory=lambda: ["Asia/Shanghai"])
    localeList: List[str] = field(default_factory=lambda: ["zh-CN"])

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ConfigLoader:
    """配置加载器 - 单例模式"""

    _instance: Optional["ConfigLoader"] = None
    _initialized: bool = False

    def __new__(cls) -> "ConfigLoader":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if ConfigLoader._initialized:
            return

        self.engines: Dict[str, EngineConfig] = {}
        self.common_config: Dict[str, Any] = {}
        self.config_dir: Optional[Path] = None
        ConfigLoader._initialized = True

    @classmethod
    def get_instance(cls) -> "ConfigLoader":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _find_config_dir(self) -> Optional[Path]:
        """查找配置文件目录"""
        possible_paths = [
            Path(__file__).parent / "engine-config",
            Path(__file__).parent.parent / "engine-config",
            Path.cwd() / "engine-config",
            Path.cwd() / "core" / "engine-config",
        ]

        # PyInstaller 打包环境：从 _MEIPASS 中查找
        if getattr(sys, 'frozen', False):
            bundle_dir = Path(sys._MEIPASS)
            possible_paths.insert(0, bundle_dir / "core" / "engine-config")
            possible_paths.insert(0, bundle_dir / "engine-config")

        for test_path in possible_paths:
            if test_path.exists() and (test_path / "common.json").exists():
                return test_path

        return None

    def load_configs(self, force: bool = False) -> None:
        """加载配置文件"""
        if self.engines and self.common_config and not force:
            return

        try:
            self.config_dir = self._find_config_dir()
            if not self.config_dir:
                raise FileNotFoundError(
                    f"无法找到配置文件目录，尝试路径：["
                    f"{Path(__file__).parent / 'engine-config'}, "
                    f"{Path.cwd() / 'engine-config'}]"
                )

            logger.info(f"使用配置文件目录：{self.config_dir}")

            # 加载通用配置
            common_config_path = self.config_dir / "common.json"
            with open(common_config_path, "r", encoding="utf-8") as f:
                self.common_config = self._strip_meta_keys(json.load(f))

            logger.info(f"加载通用配置：{common_config_path}")

            # 加载所有引擎配置
            engine_files = [f for f in self.config_dir.iterdir()
                          if f.suffix == ".json" and f.name != "common.json"]

            for engine_file in engine_files:
                try:
                    with open(engine_file, "r", encoding="utf-8") as f:
                        engine_data = self._strip_meta_keys(json.load(f))

                    # 合并默认配置
                    merged_config = self._merge_with_defaults(engine_data)
                    parsed_engine = self._build_engine_config(merged_config)
                    self.engines[parsed_engine.id] = parsed_engine
                    logger.info(f"加载引擎配置：{engine_file.name}")

                except (json.JSONDecodeError, KeyError) as e:
                    logger.error(f"加载引擎配置失败 {engine_file}: {e}")

            logger.info(f"搜索引擎配置加载完成，共加载 {len(self.engines)} 个引擎")

        except Exception as e:
            logger.error(f"加载配置文件失败：{e}")
            self._set_default_configs()

    @staticmethod
    def _strip_meta_keys(data: Dict[str, Any]) -> Dict[str, Any]:
        """去除配置中的注释/元信息字段（如 _comment）。"""
        if not isinstance(data, dict):
            return {}
        return {k: v for k, v in data.items() if not str(k).startswith("_")}

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _build_engine_config(self, engine_data: Dict[str, Any]) -> EngineConfig:
        """
        将松散 JSON 配置安全转换为 EngineConfig。
        允许存在额外字段，但只落地 dataclass 定义字段。
        """
        allowed_fields = {f.name for f in fields(EngineConfig)}
        filtered: Dict[str, Any] = {
            key: value
            for key, value in self._strip_meta_keys(engine_data).items()
            if key in allowed_fields
        }

        # 必填字段兜底检查
        required = ["id", "name", "baseUrl", "searchPath", "selectors"]
        missing = [key for key in required if key not in filtered]
        if missing:
            raise KeyError(f"缺少必要字段: {', '.join(missing)}")

        # antiBot：dict -> AntiBotConfig
        anti_bot_raw = filtered.get("antiBot", {})
        if isinstance(anti_bot_raw, AntiBotConfig):
            anti_bot = anti_bot_raw
        elif isinstance(anti_bot_raw, dict):
            anti_bot = AntiBotConfig(
                enabled=bool(anti_bot_raw.get("enabled", True)),
                detectors=list(anti_bot_raw.get("detectors", []) or []),
                errorMessage=str(
                    anti_bot_raw.get(
                        "errorMessage",
                        "搜索引擎检测到验证机制，需要人工干预。",
                    )
                ),
            )
        else:
            anti_bot = AntiBotConfig()
        filtered["antiBot"] = anti_bot

        # 容错清洗常见字段类型
        if not isinstance(filtered.get("selectors"), dict):
            filtered["selectors"] = {}
        if not isinstance(filtered.get("headers"), dict):
            filtered["headers"] = {}

        custom_delay_raw = filtered.get("customDelay", {}) or {}
        if not isinstance(custom_delay_raw, dict):
            custom_delay_raw = {}
        filtered["customDelay"] = {
            "min": self._safe_int(custom_delay_raw.get("min", 1000), 1000),
            "max": self._safe_int(custom_delay_raw.get("max", 3000), 3000),
        }

        if not isinstance(filtered.get("linkValidation"), list):
            filtered["linkValidation"] = ["http", "www"]
        if not isinstance(filtered.get("timezoneList"), list):
            filtered["timezoneList"] = ["Asia/Shanghai"]
        if not isinstance(filtered.get("localeList"), list):
            filtered["localeList"] = ["zh-CN"]
        filtered["maxResultsPerPage"] = self._safe_int(
            filtered.get("maxResultsPerPage", 10),
            10,
        )

        return EngineConfig(**filtered)

    def _merge_with_defaults(self, engine_config: Dict[str, Any]) -> Dict[str, Any]:
        """合并默认配置"""
        if not self.common_config:
            raise ValueError("通用配置未加载")

        # 合并 headers
        headers = {**self.common_config.get("defaultHeaders", {})}
        if "headers" in engine_config:
            headers.update(engine_config["headers"])

        # 合并 antiBot
        default_anti_bot = dict(self.common_config.get("defaultAntiBot", {}))
        if "antiBot" in engine_config:
            default_anti_bot.update(engine_config["antiBot"])

        # 合并 delay
        default_delay = dict(self.common_config.get("defaultDelay", {"min": 1000, "max": 3000}))
        if "customDelay" in engine_config:
            default_delay.update(engine_config["customDelay"])

        return {
            "fallbackSelector": self.common_config.get(
                "defaultFallbackSelector", 'div:has(a[href*="http"])'
            ),
            "linkValidation": self.common_config.get(
                "defaultLinkValidation", ["http", "www"]
            ),
            **engine_config,
            "headers": headers,
            "antiBot": default_anti_bot,
            "customDelay": default_delay,
        }

    def _set_default_configs(self) -> None:
        """设置默认配置（当配置文件加载失败时）"""
        self.common_config = self.common_config or {}
        default_engines = [
            {
                "id": "google",
                "name": "Google",
                "baseUrl": "https://www.google.com",
                "searchPath": "/search?q=",
                "selectors": {
                    "resultContainer": ".g",
                    "title": "h3",
                    "link": "a",
                    "snippet": ".VwiC3b",
                },
            },
            {
                "id": "baidu",
                "name": "百度",
                "baseUrl": "https://www.baidu.com",
                "searchPath": "/s?wd=",
                "selectors": {
                    "resultContainer": "div.result",
                    "title": "h3 a",
                    "link": "a",
                    "snippet": ".c-abstract",
                },
            },
            {
                "id": "bing",
                "name": "Bing",
                "baseUrl": "https://www.bing.com",
                "searchPath": "/search?q=",
                "selectors": {
                    "resultContainer": "li.b_algo",
                    "title": "h2 a",
                    "link": "a",
                    "snippet": ".b_caption",
                },
            },
            {
                "id": "quark",
                "name": "夸克",
                "baseUrl": "https://www.quark.cn",
                "searchPath": "/s?q=",
                "selectors": {
                    "resultContainer": "div[class*='result'], .search-content .results",
                    "title": "a.qk-link-wrapper, a[href^='http']",
                    "link": "a.qk-link-wrapper, a[href^='http']",
                    "snippet": "div[class*='desc'], p",
                },
            },
        ]

        for engine_data in default_engines:
            parsed_engine = self._build_engine_config({
                **engine_data,
                "headers": self.common_config.get("defaultHeaders", {}),
                "antiBot": self.common_config.get("defaultAntiBot", {}),
                "customDelay": self.common_config.get("defaultDelay", {}),
            })
            self.engines[parsed_engine.id] = parsed_engine

    def get_engine_config(self, engine_id: str) -> Optional[EngineConfig]:
        """获取引擎配置"""
        self.load_configs()
        return self.engines.get(engine_id)

    def get_supported_engines_ids(self) -> List[str]:
        """获取所有支持的引擎 ID"""
        self.load_configs()
        return list(self.engines.keys())

    def is_engine_supported(self, engine_id: str) -> bool:
        """检查引擎是否被支持"""
        self.load_configs()
        return engine_id in self.engines

    def get_fallback_selector(self, engine_id: str) -> str:
        """获取备用选择器"""
        config = self.get_engine_config(engine_id)
        if config and hasattr(config, "fallbackSelector"):
            return config.fallbackSelector
        return 'div:has(a[href*="http"])'

    def get_link_validation_rules(self, engine_id: str) -> List[str]:
        """获取链接验证规则"""
        config = self.get_engine_config(engine_id)
        if config and hasattr(config, "linkValidation"):
            return config.linkValidation
        return ["http"]

    def get_anti_bot_detectors(self, engine_id: str) -> List[str]:
        """获取反爬虫检测器列表"""
        config = self.get_engine_config(engine_id)
        if config and hasattr(config, "antiBot"):
            anti_bot = config.antiBot
            if isinstance(anti_bot, dict):
                return list(anti_bot.get("detectors", []) or [])
            return list(getattr(anti_bot, "detectors", []) or [])
        return []

    def get_anti_bot_error_message(self, engine_id: str) -> str:
        """获取反爬虫错误消息"""
        config = self.get_engine_config(engine_id)
        if config and hasattr(config, "antiBot"):
            anti_bot = config.antiBot
            if isinstance(anti_bot, dict):
                return str(anti_bot.get("errorMessage", f"{engine_id}需要人工验证，请手动完成后重试。"))
            return str(getattr(anti_bot, "errorMessage", f"{engine_id}需要人工验证，请手动完成后重试。"))
        return f"{engine_id}需要人工验证，请手动完成后重试。"

    def is_anti_bot_enabled(self, engine_id: str) -> bool:
        """检查是否启用反爬虫检测"""
        config = self.get_engine_config(engine_id)
        if config and hasattr(config, "antiBot"):
            anti_bot = config.antiBot
            if isinstance(anti_bot, dict):
                return bool(anti_bot.get("enabled", False))
            return bool(getattr(anti_bot, "enabled", False))
        return False

    def get_custom_delay(self, engine_id: str) -> Dict[str, int]:
        """获取自定义延迟配置"""
        config = self.get_engine_config(engine_id)
        if config and hasattr(config, "customDelay"):
            return config.customDelay
        return {"min": 1000, "max": 3000}

    def get_selectors(self, engine_id: str) -> Dict[str, str]:
        """获取选择器配置"""
        config = self.get_engine_config(engine_id)
        if config and hasattr(config, "selectors"):
            return config.selectors
        return {
            "resultContainer": "div.result",
            "title": "h3 a",
            "link": "a",
            "snippet": "p",
        }

    def get_headers(self, engine_id: str) -> Dict[str, str]:
        """获取 HTTP 头配置"""
        config = self.get_engine_config(engine_id)
        if config and hasattr(config, "headers"):
            return config.headers
        return {}

    def get_timezones(self, engine_id: str) -> List[str]:
        """获取时区列表"""
        config = self.get_engine_config(engine_id)
        if config and hasattr(config, "timezoneList"):
            return config.timezoneList
        return ["Asia/Shanghai"]

    def get_locales(self, engine_id: str) -> List[str]:
        """获取语言列表"""
        config = self.get_engine_config(engine_id)
        if config and hasattr(config, "localeList"):
            return config.localeList
        return ["zh-CN"]

    def reload_config(self) -> None:
        """重新加载配置（用于热更新）"""
        self.engines.clear()
        self.common_config.clear()
        self.load_configs(force=True)
        logger.info("搜索引擎配置已重新加载")


# 便捷函数
def get_engine_config(engine_id: str) -> Optional[EngineConfig]:
    """快速获取引擎配置"""
    return ConfigLoader.get_instance().get_engine_config(engine_id)


def get_supported_engines() -> List[str]:
    """获取所有支持的引擎"""
    return ConfigLoader.get_instance().get_supported_engines_ids()

