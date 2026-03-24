"""
Web-Rooter Cookie 同步核心模块

自动检测和提取本机浏览器 Cookie，生成符合 Web-Rooter 标准的登录配置。

支持的浏览器:
- Safari (macOS)
- Chrome (macOS/Windows/Linux)
- Edge (macOS/Windows/Linux)
- Firefox (macOS/Windows/Linux)
- Brave (macOS/Windows/Linux)

生成的配置格式完全兼容 Web-Rooter 的 auth_profiles 系统。
"""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import struct
import sys
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from core.auth_profiles import AuthProfile, get_auth_profile_registry

logger = logging.getLogger(__name__)

# Mac Epoch 偏移（1970-01-01 到 2001-01-01 的秒数）
MAC_EPOCH_OFFSET = 978307200


@dataclass
class BrowserCookie:
    """标准化的浏览器 Cookie"""
    name: str
    value: str
    domain: str
    path: str = "/"
    expires: Optional[float] = None
    secure: bool = False
    http_only: bool = False
    same_site: Optional[str] = None
    
    def to_playwright_format(self) -> Dict[str, Any]:
        """转换为 Playwright add_cookies 格式"""
        cookie: Dict[str, Any] = {
            "name": self.name,
            "value": self.value,
            "domain": self.domain,
            "path": self.path,
        }
        if self.expires:
            cookie["expires"] = self.expires
        if self.secure:
            cookie["secure"] = self.secure
        if self.http_only:
            cookie["httpOnly"] = self.http_only
        if self.same_site:
            cookie["sameSite"] = self.same_site
        return cookie
    
    def to_auth_profile_format(self) -> Dict[str, Any]:
        """转换为 Web-Rooter auth_profile Cookie 格式"""
        cookie: Dict[str, Any] = {
            "name": self.name,
            "value": self.value,
            "domain": self.domain,
            "path": self.path,
        }
        if self.expires:
            cookie["expires"] = self.expires
        if self.secure:
            cookie["secure"] = self.secure
        if self.http_only:
            cookie["httpOnly"] = self.http_only
        if self.same_site:
            cookie["sameSite"] = self.same_site
        return cookie


@dataclass
class BrowserInfo:
    """浏览器信息"""
    name: str
    identifier: str  # 内部标识符
    cookie_file: Optional[Path] = None
    key_file: Optional[Path] = None  # Chromium 的 Local State
    profile_dir: Optional[Path] = None
    is_chromium: bool = False
    is_available: bool = False
    

class CookieExtractor(ABC):
    """Cookie 提取器基类"""
    
    def __init__(self, browser_info: BrowserInfo):
        self.browser_info = browser_info
    
    @abstractmethod
    def extract_cookies(self, domain_filter: Optional[str] = None) -> List[BrowserCookie]:
        """提取所有 Cookie"""
        pass
    
    def extract_for_domains(self, domains: List[str]) -> List[BrowserCookie]:
        """提取指定域名的 Cookie"""
        all_cookies = self.extract_cookies()
        result = []
        for cookie in all_cookies:
            for domain in domains:
                if self._domain_matches(cookie.domain, domain):
                    result.append(cookie)
                    break
        return result
    
    @staticmethod
    def _domain_matches(cookie_domain: str, target_domain: str) -> bool:
        """检查 Cookie 域名是否匹配目标域名"""
        cookie_domain = cookie_domain.lower().strip()
        target_domain = target_domain.lower().strip()
        
        # 去除前导点
        cookie_domain = cookie_domain.lstrip(".")
        target_domain = target_domain.lstrip(".")
        
        # 完全匹配
        if cookie_domain == target_domain:
            return True
        
        # 子域名匹配
        if target_domain.endswith(cookie_domain) or cookie_domain.endswith(target_domain):
            return True
        
        return False


class SafariCookieExtractor(CookieExtractor):
    """Safari Cookie 提取器 (macOS 专属)"""
    
    # Safari Cookie 文件路径
    COOKIE_PATHS = [
        Path.home() / "Library/Containers/com.apple.Safari/Data/Library/Cookies/Cookies.binarycookies",
        Path.home() / "Library/Cookies/Cookies.binarycookies",
    ]
    
    def __init__(self):
        cookie_file = self._find_cookie_file()
        info = BrowserInfo(
            name="Safari",
            identifier="safari",
            cookie_file=cookie_file,
            is_available=cookie_file is not None
        )
        super().__init__(info)
    
    @classmethod
    def _find_cookie_file(cls) -> Optional[Path]:
        """查找 Safari Cookie 文件"""
        for path in cls.COOKIE_PATHS:
            if path.exists():
                try:
                    with open(path, "rb") as f:
                        f.read(4)
                    return path
                except PermissionError:
                    continue
                except Exception:
                    continue
        return None
    
    def extract_cookies(self, domain_filter: Optional[str] = None) -> List[BrowserCookie]:
        """提取 Safari Cookie"""
        if not self.browser_info.cookie_file:
            raise FileNotFoundError("未找到 Safari Cookie 文件。请确保已授予完全磁盘访问权限。")
        
        with open(self.browser_info.cookie_file, "rb") as f:
            data = f.read()
        
        return self._parse_binary_cookies(data, domain_filter)
    
    def _parse_binary_cookies(self, data: bytes, domain_filter: Optional[str] = None) -> List[BrowserCookie]:
        """解析二进制 Cookie 数据"""
        cookies = []
        
        if len(data) < 4 or data[0:4].decode("ascii", errors="ignore") != "cook":
            raise ValueError("无效的二进制 Cookie 文件")
        
        position = 4
        num_pages = struct.unpack(">I", data[position:position + 4])[0]
        position += 4
        
        # 读取页大小
        page_sizes = []
        for _ in range(num_pages):
            page_size = struct.unpack(">I", data[position:position + 4])[0]
            page_sizes.append(page_size)
            position += 4
        
        # 解析每页
        for page_size in page_sizes:
            page_data = data[position:position + page_size]
            page_cookies = self._parse_page(page_data, domain_filter)
            cookies.extend(page_cookies)
            position += page_size
        
        return cookies
    
    def _parse_page(self, page_data: bytes, domain_filter: Optional[str] = None) -> List[BrowserCookie]:
        """解析单页数据"""
        cookies = []
        
        if len(page_data) < 8:
            return cookies
        
        page_header = struct.unpack(">I", page_data[0:4])[0]
        if page_header != 256:
            return cookies
        
        num_cookies = struct.unpack("<I", page_data[4:8])[0]
        
        # 读取偏移量
        offsets = []
        offset_start = 8
        for i in range(num_cookies):
            offset_pos = offset_start + i * 4
            if len(page_data) < offset_pos + 4:
                break
            offset = struct.unpack("<I", page_data[offset_pos:offset_pos + 4])[0]
            offsets.append(offset)
        
        # 解析每个 Cookie
        for offset in offsets:
            try:
                cookie = self._parse_cookie(page_data, offset)
                if cookie:
                    if domain_filter is None or domain_filter.lower() in cookie.domain.lower():
                        cookies.append(cookie)
            except Exception:
                continue
        
        return cookies
    
    def _parse_cookie(self, page_data: bytes, offset: int) -> Optional[BrowserCookie]:
        """解析单个 Cookie"""
        if offset >= len(page_data):
            return None
        
        if offset + 4 > len(page_data):
            return None
        
        cookie_size = struct.unpack("<I", page_data[offset:offset + 4])[0]
        if cookie_size == 0 or offset + cookie_size > len(page_data):
            return None
        
        cookie_data = page_data[offset:offset + cookie_size]
        
        if len(cookie_data) < 8:
            return None
        
        flags = struct.unpack("<I", cookie_data[4:8])[0]
        
        if len(cookie_data) < 32:
            return None
        
        # 读取字符串偏移表（修正后的偏移量）
        url_offset = struct.unpack("<I", cookie_data[16:20])[0]
        name_offset = struct.unpack("<I", cookie_data[20:24])[0]
        path_offset = struct.unpack("<I", cookie_data[24:28])[0]
        value_offset = struct.unpack("<I", cookie_data[28:32])[0]
        
        # 读取时间戳
        expires = None
        if len(cookie_data) >= 48:
            try:
                expiration_ts = struct.unpack("<d", cookie_data[40:48])[0] + MAC_EPOCH_OFFSET
                expires = expiration_ts
            except Exception:
                pass
        
        # 读取字符串
        url = self._read_string(cookie_data, url_offset)
        name = self._read_string(cookie_data, name_offset)
        path = self._read_string(cookie_data, path_offset)
        value = self._read_string(cookie_data, value_offset)
        
        if not name:
            return None
        
        return BrowserCookie(
            name=name,
            value=value,
            domain=url,
            path=path,
            expires=expires,
            secure=bool(flags & 1),
            http_only=bool(flags & 4),
        )
    
    def _read_string(self, data: bytes, offset: int) -> str:
        """读取 null 结尾的字符串"""
        if offset >= len(data) or offset < 0:
            return ""
        
        end = offset
        while end < len(data) and data[end] != 0:
            end += 1
        
        try:
            return data[offset:end].decode("utf-8", errors="replace").strip()
        except Exception:
            return ""


class ChromiumCookieExtractor(CookieExtractor):
    """Chromium 系列浏览器 Cookie 提取器"""
    
    # Chromium 浏览器配置
    CHROMIUM_BROWSERS = {
        "chrome": {
            "name": "Chrome",
            "paths": {
                "darwin": [
                    Path.home() / "Library/Application Support/Google/Chrome/Default/Cookies",
                    Path.home() / "Library/Application Support/Google/Chrome/Profile */Cookies",
                ],
                "win32": [
                    Path.home() / "AppData/Local/Google/Chrome/User Data/Default/Network/Cookies",
                    Path.home() / "AppData/Local/Google/Chrome/User Data/Default/Cookies",
                ],
                "linux": [
                    Path.home() / ".config/google-chrome/Default/Cookies",
                ],
            },
            "local_state": {
                "darwin": Path.home() / "Library/Application Support/Google/Chrome/Local State",
                "win32": Path.home() / "AppData/Local/Google/Chrome/User Data/Local State",
                "linux": Path.home() / ".config/google-chrome/Local State",
            },
            "storage_name": "Chrome Safe Storage",
        },
        "edge": {
            "name": "Edge",
            "paths": {
                "darwin": [
                    Path.home() / "Library/Application Support/Microsoft Edge/Default/Cookies",
                ],
                "win32": [
                    Path.home() / "AppData/Local/Microsoft/Edge/User Data/Default/Network/Cookies",
                ],
                "linux": [
                    Path.home() / ".config/microsoft-edge/Default/Cookies",
                ],
            },
            "local_state": {
                "darwin": Path.home() / "Library/Application Support/Microsoft Edge/Local State",
                "win32": Path.home() / "AppData/Local/Microsoft/Edge/User Data/Local State",
                "linux": Path.home() / ".config/microsoft-edge/Local State",
            },
            "storage_name": "Microsoft Edge Safe Storage",
        },
        "brave": {
            "name": "Brave",
            "paths": {
                "darwin": [
                    Path.home() / "Library/Application Support/BraveSoftware/Brave-Browser/Default/Cookies",
                ],
                "win32": [
                    Path.home() / "AppData/Local/BraveSoftware/Brave-Browser/User Data/Default/Network/Cookies",
                ],
                "linux": [
                    Path.home() / ".config/BraveSoftware/Brave-Browser/Default/Cookies",
                ],
            },
            "local_state": {
                "darwin": Path.home() / "Library/Application Support/BraveSoftware/Brave-Browser/Local State",
                "win32": Path.home() / "AppData/Local/BraveSoftware/Brave-Browser/User Data/Local State",
                "linux": Path.home() / ".config/BraveSoftware/Brave-Browser/Local State",
            },
            "storage_name": "Brave Safe Storage",
        },
    }
    
    def __init__(self, browser_id: str):
        self.browser_id = browser_id.lower()
        self.config = self.CHROMIUM_BROWSERS.get(self.browser_id)
        
        if not self.config:
            raise ValueError(f"不支持的 Chromium 浏览器: {browser_id}")
        
        cookie_file = self._find_cookie_file()
        key_file = self._get_key_file()
        
        info = BrowserInfo(
            name=self.config["name"],
            identifier=browser_id,
            cookie_file=cookie_file,
            key_file=key_file,
            is_chromium=True,
            is_available=cookie_file is not None
        )
        super().__init__(info)
        self._master_key: Optional[bytes] = None
    
    def _find_cookie_file(self) -> Optional[Path]:
        """查找 Cookie 文件"""
        platform_paths = self.config["paths"].get(sys.platform, [])
        for pattern in platform_paths:
            if "*" in str(pattern):
                # 处理通配符
                parent = pattern.parent
                if parent.exists():
                    for child in parent.iterdir():
                        candidate = child / "Cookies" if "Profile" in str(child) else child
                        if candidate.exists():
                            return candidate
            elif pattern.exists():
                return pattern
        return None
    
    def _get_key_file(self) -> Optional[Path]:
        """获取 Local State 文件路径"""
        local_state_paths = self.config.get("local_state", {})
        path = local_state_paths.get(sys.platform)
        return path if path and path.exists() else None
    
    def extract_cookies(self, domain_filter: Optional[str] = None) -> List[BrowserCookie]:
        """提取 Chromium Cookie"""
        if not self.browser_info.cookie_file:
            raise FileNotFoundError(f"未找到 {self.browser_info.name} Cookie 文件")
        
        # 复制到临时位置避免锁定
        temp_db = self._copy_db_to_temp(str(self.browser_info.cookie_file))
        
        try:
            cookies = []
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            
            try:
                cursor.execute("""
                    SELECT host_key, name, value, encrypted_value, path, expires_utc, 
                           is_secure, is_httponly, samesite
                    FROM cookies
                """)
                
                for row in cursor.fetchall():
                    try:
                        host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly, samesite = row
                        
                        # 解密值
                        if encrypted_value and len(encrypted_value) > 0:
                            try:
                                value = self._decrypt_value(encrypted_value)
                            except Exception:
                                value = ""
                        
                        if not value:
                            continue
                        
                        # 转换过期时间 (Chromium 使用 1601-01-01 作为起点，单位是微秒)
                        expires = None
                        if expires_utc and expires_utc > 0:
                            expires = (expires_utc / 1000000) - 11644473600
                        
                        # 转换 SameSite
                        same_site = None
                        if samesite == 1:
                            same_site = "Lax"
                        elif samesite == 2:
                            same_site = "Strict"
                        elif samesite == 3:
                            same_site = "None"
                        
                        cookie = BrowserCookie(
                            name=name,
                            value=value,
                            domain=host_key,
                            path=path or "/",
                            expires=expires,
                            secure=bool(is_secure),
                            http_only=bool(is_httponly),
                            same_site=same_site,
                        )
                        
                        if domain_filter is None or domain_filter.lower() in cookie.domain.lower():
                            cookies.append(cookie)
                            
                    except Exception as e:
                        logger.debug(f"解析 Cookie 失败: {e}")
                        continue
                
            except sqlite3.OperationalError as e:
                logger.warning(f"查询 Cookie 数据库失败: {e}")
            
            conn.close()
            return cookies
            
        finally:
            Path(temp_db).unlink(missing_ok=True)
    
    def _copy_db_to_temp(self, db_path: str) -> str:
        """复制数据库到临时位置"""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        temp_file.close()
        shutil.copy2(db_path, temp_file.name)
        return temp_file.name
    
    def _decrypt_value(self, encrypted_value: bytes) -> str:
        """解密 Cookie 值（简化版，仅处理明文）"""
        # 如果值不以 v10 或 v11 开头，可能是明文
        if not encrypted_value.startswith((b"v10", b"v11")):
            try:
                return encrypted_value.decode("utf-8")
            except Exception:
                pass
        
        # 尝试获取主密钥解密（如果可用）
        try:
            key = self._get_master_key()
            if key and sys.platform == "darwin":
                return self._decrypt_macos(encrypted_value, key)
        except Exception as e:
            logger.debug(f"解密失败: {e}")
        
        return ""
    
    def _get_master_key(self) -> Optional[bytes]:
        """获取主密钥（macOS 专用）"""
        if self._master_key is not None:
            return self._master_key
        
        if sys.platform != "darwin":
            return None
        
        if not self.browser_info.key_file:
            return None
        
        try:
            import base64
            from core.keychain import get_chromium_key
            
            with open(self.browser_info.key_file, "r") as f:
                local_state = json.load(f)
            
            encrypted_key = local_state.get("os_crypt", {}).get("encrypted_key")
            if not encrypted_key:
                return None
            
            key_data = base64.b64decode(encrypted_key)[5:]  # 移除 DPAPI 前缀
            
            # 尝试从 keychain 获取密钥
            storage_name = self.config.get("storage_name", "")
            self._master_key = get_chromium_key(storage_name)
            return self._master_key
            
        except Exception as e:
            logger.debug(f"获取主密钥失败: {e}")
            return None
    
    def _decrypt_macos(self, encrypted_value: bytes, key: bytes) -> str:
        """解密 macOS 上的 Chromium Cookie"""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            
            if encrypted_value.startswith(b"v10"):
                encrypted_value = encrypted_value[3:]
            elif encrypted_value.startswith(b"v11"):
                encrypted_value = encrypted_value[3:]
            else:
                return ""
            
            nonce = encrypted_value[:12]
            ciphertext = encrypted_value[12:-16]
            tag = encrypted_value[-16:]
            
            aesgcm = AESGCM(key)
            decrypted = aesgcm.decrypt(nonce, ciphertext + tag, None)
            return decrypted.decode("utf-8")
            
        except Exception as e:
            logger.debug(f"AES-GCM 解密失败: {e}")
            return ""


class FirefoxCookieExtractor(CookieExtractor):
    """Firefox Cookie 提取器"""
    
    # Firefox 配置路径
    FIREFOX_PATHS = {
        "darwin": [
            Path.home() / "Library/Application Support/Firefox/Profiles",
        ],
        "win32": [
            Path.home() / "AppData/Roaming/Mozilla/Firefox/Profiles",
        ],
        "linux": [
            Path.home() / ".mozilla/firefox",
        ],
    }
    
    def __init__(self, profile_path: Optional[Path] = None):
        if profile_path:
            self.profile_path = profile_path
            self.profile_name = profile_path.name
        else:
            self.profile_path, self.profile_name = self._find_default_profile()
        
        cookie_file = self.profile_path / "cookies.sqlite" if self.profile_path else None
        
        info = BrowserInfo(
            name="Firefox",
            identifier="firefox",
            cookie_file=cookie_file,
            profile_dir=self.profile_path,
            is_available=cookie_file is not None and cookie_file.exists()
        )
        super().__init__(info)
    
    @classmethod
    def _find_default_profile(cls) -> Tuple[Optional[Path], str]:
        """查找默认 Firefox 配置文件"""
        profiles_dir = cls.FIREFOX_PATHS.get(sys.platform, [])
        
        for base_dir in profiles_dir:
            if not base_dir.exists():
                continue
            
            # 查找 profiles.ini
            profiles_ini = base_dir.parent / "profiles.ini" if "Profiles" in str(base_dir) else base_dir / "profiles.ini"
            
            if profiles_ini.exists():
                # 解析 profiles.ini
                current_profile = None
                with open(profiles_ini, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("Path="):
                            current_profile = line[5:]
                        elif line.startswith("Default=1") and current_profile:
                            profile_path = base_dir / current_profile
                            if profile_path.exists():
                                return profile_path, current_profile
            
            # 如果没有找到默认配置，返回第一个
            for item in base_dir.iterdir():
                if item.is_dir() and ".default" in item.name:
                    return item, item.name
        
        return None, ""
    
    def extract_cookies(self, domain_filter: Optional[str] = None) -> List[BrowserCookie]:
        """提取 Firefox Cookie"""
        if not self.browser_info.cookie_file or not self.browser_info.cookie_file.exists():
            raise FileNotFoundError("未找到 Firefox Cookie 文件")
        
        # 复制到临时位置
        temp_db = self._copy_db_to_temp(str(self.browser_info.cookie_file))
        
        try:
            cookies = []
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            
            try:
                cursor.execute("""
                    SELECT host, name, value, path, expiry, isSecure, isHttpOnly, sameSite
                    FROM moz_cookies
                """)
                
                for row in cursor.fetchall():
                    try:
                        host, name, value, path, expiry, is_secure, is_http_only, same_site = row
                        
                        # 转换过期时间 (Unix 时间戳)
                        expires = None
                        if expiry and expiry > 0:
                            expires = float(expiry)
                        
                        cookie = BrowserCookie(
                            name=name,
                            value=value,
                            domain=host,
                            path=path or "/",
                            expires=expires,
                            secure=bool(is_secure),
                            http_only=bool(is_http_only),
                            same_site=same_site if same_site else None,
                        )
                        
                        if domain_filter is None or domain_filter.lower() in cookie.domain.lower():
                            cookies.append(cookie)
                            
                    except Exception as e:
                        logger.debug(f"解析 Cookie 失败: {e}")
                        continue
                
            except sqlite3.OperationalError as e:
                logger.warning(f"查询 Cookie 数据库失败: {e}")
            
            conn.close()
            return cookies
            
        finally:
            Path(temp_db).unlink(missing_ok=True)
    
    def _copy_db_to_temp(self, db_path: str) -> str:
        """复制数据库到临时位置"""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        temp_file.close()
        shutil.copy2(db_path, temp_file.name)
        return temp_file.name


class CookieSyncManager:
    """Cookie 同步管理器"""
    
    # 平台域名映射
    PLATFORM_DOMAINS = {
        "xiaohongshu": ["xiaohongshu.com", "xhslink.com", "edith.xiaohongshu.com"],
        "zhihu": ["zhihu.com", "www.zhihu.com"],
        "bilibili": ["bilibili.com", "www.bilibili.com"],
        "weibo": ["weibo.com", "weibo.cn", "www.weibo.com"],
        "douyin": ["douyin.com", "www.douyin.com", "iesdouyin.com"],
    }
    
    def __init__(self):
        self.extractors: Dict[str, CookieExtractor] = {}
        self._init_extractors()
    
    def _init_extractors(self):
        """初始化所有可用的提取器"""
        # Safari (仅 macOS)
        if sys.platform == "darwin":
            try:
                safari = SafariCookieExtractor()
                if safari.browser_info.is_available:
                    self.extractors["safari"] = safari
                    logger.info("Safari Cookie 提取器已就绪")
            except Exception as e:
                logger.debug(f"Safari 初始化失败: {e}")
        
        # Chromium 系列
        for browser_id in ["chrome", "edge", "brave"]:
            try:
                extractor = ChromiumCookieExtractor(browser_id)
                if extractor.browser_info.is_available:
                    self.extractors[browser_id] = extractor
                    logger.info(f"{extractor.browser_info.name} Cookie 提取器已就绪")
            except Exception as e:
                logger.debug(f"{browser_id} 初始化失败: {e}")
        
        # Firefox
        try:
            firefox = FirefoxCookieExtractor()
            if firefox.browser_info.is_available:
                self.extractors["firefox"] = firefox
                logger.info("Firefox Cookie 提取器已就绪")
        except Exception as e:
            logger.debug(f"Firefox 初始化失败: {e}")
    
    def get_available_browsers(self) -> List[str]:
        """获取所有可用的浏览器"""
        return list(self.extractors.keys())
    
    def extract_all_cookies(
        self,
        domain_filter: Optional[str] = None,
        browser_filter: Optional[List[str]] = None
    ) -> Dict[str, List[BrowserCookie]]:
        """从所有可用浏览器提取 Cookie"""
        results = {}
        
        for browser_id, extractor in self.extractors.items():
            if browser_filter and browser_id not in browser_filter:
                continue
            
            try:
                cookies = extractor.extract_cookies(domain_filter)
                if cookies:
                    results[browser_id] = cookies
            except Exception as e:
                logger.warning(f"从 {browser_id} 提取 Cookie 失败: {e}")
        
        return results
    
    def extract_platform_cookies(
        self,
        platform: str,
        browser_filter: Optional[List[str]] = None
    ) -> Dict[str, List[BrowserCookie]]:
        """提取指定平台的所有 Cookie"""
        domains = self.PLATFORM_DOMAINS.get(platform.lower(), [platform])
        results = {}
        
        for browser_id, extractor in self.extractors.items():
            if browser_filter and browser_id not in browser_filter:
                continue
            
            try:
                cookies = []
                for domain in domains:
                    domain_cookies = extractor.extract_for_domains([domain])
                    # 去重
                    seen = set()
                    for c in domain_cookies:
                        key = (c.name, c.domain)
                        if key not in seen:
                            seen.add(key)
                            cookies.append(c)
                
                if cookies:
                    results[browser_id] = cookies
            except Exception as e:
                logger.warning(f"从 {browser_id} 提取 {platform} Cookie 失败: {e}")
        
        return results
    
    def generate_auth_profile(
        self,
        platform: str,
        browser_id: Optional[str] = None,
        output_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        生成 Web-Rooter 标准的 auth_profile 配置
        
        Args:
            platform: 平台标识，如 "xiaohongshu", "zhihu"
            browser_id: 指定浏览器，None 则使用第一个可用的
            output_path: 输出路径，None 则使用默认路径
            
        Returns:
            生成的配置信息
        """
        # 获取平台域名
        domains = self.PLATFORM_DOMAINS.get(platform.lower(), [platform])
        primary_domain = domains[0]
        
        # 提取 Cookie
        if browser_id:
            if browser_id not in self.extractors:
                raise ValueError(f"浏览器 {browser_id} 不可用")
            extractors_to_try = {browser_id: self.extractors[browser_id]}
        else:
            # 优先使用 Safari (macOS)，然后是 Chrome
            extractors_to_try = {}
            preferred_order = ["safari", "chrome", "edge", "brave", "firefox"]
            for bid in preferred_order:
                if bid in self.extractors:
                    extractors_to_try[bid] = self.extractors[bid]
                    break
            if not extractors_to_try:
                extractors_to_try = self.extractors
        
        all_cookies: List[BrowserCookie] = []
        source_browser = ""
        
        for bid, extractor in extractors_to_try.items():
            try:
                cookies = []
                seen = set()
                for domain in domains:
                    domain_cookies = extractor.extract_for_domains([domain])
                    for c in domain_cookies:
                        key = (c.name, c.domain)
                        if key not in seen:
                            seen.add(key)
                            cookies.append(c)
                
                if cookies:
                    all_cookies = cookies
                    source_browser = extractor.browser_info.name
                    break
            except Exception as e:
                logger.debug(f"从 {bid} 提取失败: {e}")
        
        if not all_cookies:
            return {
                "success": False,
                "platform": platform,
                "error": f"未找到 {platform} 的登录 Cookie。请确保已在浏览器中登录。",
            }
        
        # 构建 auth_profile 格式
        profile_name = f"{platform}_{source_browser.lower()}_auth"
        
        # 转换 Cookie 格式
        cookie_list = [c.to_auth_profile_format() for c in all_cookies]
        
        # 构建完整的登录态配置
        profile = {
            "name": profile_name,
            "enabled": True,
            "priority": 220,
            "domains": domains,
            "mode": "cookies",
            "login_url": f"https://www.{primary_domain}" if not primary_domain.startswith("www.") else f"https://{primary_domain}",
            "headers": {
                "User-Agent": self._get_user_agent(source_browser.lower()),
                "Referer": f"https://www.{primary_domain}/" if not primary_domain.startswith("www.") else f"https://{primary_domain}/",
            },
            "cookies": cookie_list,
            "local_storage": {},
            "notes": f"Auto-extracted from {source_browser} browser",
        }
        
        # 确定输出路径
        if output_path is None:
            output_path = Path.cwd() / ".web-rooter" / "login_profiles.json"
        else:
            output_path = Path(output_path)
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 读取现有配置或创建新配置
        existing_profiles = []
        if output_path.exists():
            try:
                with open(output_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    existing_profiles = data.get("profiles", [])
                    # 移除同名 profile
                    existing_profiles = [p for p in existing_profiles if p.get("name") != profile_name]
            except Exception as e:
                logger.warning(f"读取现有配置失败: {e}")
        
        # 添加新 profile
        existing_profiles.append(profile)
        
        # 写入配置
        config = {
            "version": 1,
            "notes": "Auto-generated by wr cookie command",
            "profiles": existing_profiles,
        }
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        return {
            "success": True,
            "platform": platform,
            "browser": source_browser,
            "profile_name": profile_name,
            "output_path": str(output_path),
            "cookies_count": len(cookie_list),
            "domains": domains,
        }
    
    def _get_user_agent(self, browser: str) -> str:
        """获取浏览器的 User-Agent"""
        uas = {
            "safari": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15",
            "chrome": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            "edge": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0",
            "brave": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            "firefox": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:136.0) Gecko/20100101 Firefox/136.0",
        }
        return uas.get(browser.lower(), uas["chrome"])


# 全局管理器实例
_cookie_sync_manager: Optional[CookieSyncManager] = None


def get_cookie_sync_manager() -> CookieSyncManager:
    """获取 Cookie 同步管理器实例"""
    global _cookie_sync_manager
    if _cookie_sync_manager is None:
        _cookie_sync_manager = CookieSyncManager()
    return _cookie_sync_manager
