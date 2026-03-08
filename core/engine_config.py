"""
搜索引擎配置加载器 - 单例模式
灵感来自 playwright-search-mcp 项目

功能:
- 加载 JSON 配置文件
- 合并默认配置和引擎特定配置
- 提供配置访问接口
- 支持配置热重载
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
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
                self.common_config = json.load(f)

            logger.info(f"加载通用配置：{common_config_path}")

            # 加载所有引擎配置
            engine_files = [f for f in self.config_dir.iterdir()
                          if f.suffix == ".json" and f.name != "common.json"]

            for engine_file in engine_files:
                try:
                    with open(engine_file, "r", encoding="utf-8") as f:
                        engine_data = json.load(f)

                    # 合并默认配置
                    merged_config = self._merge_with_defaults(engine_data)
                    self.engines[merged_config["id"]] = EngineConfig(**merged_config)
                    logger.info(f"加载引擎配置：{engine_file.name}")

                except (json.JSONDecodeError, KeyError) as e:
                    logger.error(f"加载引擎配置失败 {engine_file}: {e}")

            logger.info(f"搜索引擎配置加载完成，共加载 {len(self.engines)} 个引擎")

        except Exception as e:
            logger.error(f"加载配置文件失败：{e}")
            self._set_default_configs()

    def _merge_with_defaults(self, engine_config: Dict[str, Any]) -> Dict[str, Any]:
        """合并默认配置"""
        if not self.common_config:
            raise ValueError("通用配置未加载")

        # 合并 headers
        headers = {**self.common_config.get("defaultHeaders", {})}
        if "headers" in engine_config:
            headers.update(engine_config["headers"])

        # 合并 antiBot
        default_anti_bot = self.common_config.get("defaultAntiBot", {})
        if "antiBot" in engine_config:
            default_anti_bot.update(engine_config["antiBot"])

        # 合并 delay
        default_delay = self.common_config.get("defaultDelay", {"min": 1000, "max": 3000})
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
        ]

        for engine_data in default_engines:
            self.engines[engine_data["id"]] = EngineConfig(**{
                **engine_data,
                "headers": self.common_config.get("defaultHeaders", {}),
                "antiBot": self.common_config.get("defaultAntiBot", {}),
                "customDelay": self.common_config.get("defaultDelay", {}),
            })

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
            return config.antiBot.detectors
        return []

    def get_anti_bot_error_message(self, engine_id: str) -> str:
        """获取反爬虫错误消息"""
        config = self.get_engine_config(engine_id)
        if config and hasattr(config, "antiBot"):
            return config.antiBot.errorMessage
        return f"{engine_id}需要人工验证，请手动完成后重试。"

    def is_anti_bot_enabled(self, engine_id: str) -> bool:
        """检查是否启用反爬虫检测"""
        config = self.get_engine_config(engine_id)
        if config and hasattr(config, "antiBot"):
            return config.antiBot.enabled
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
