"""
浏览器数据路径配置
支持 macOS, Windows, Linux
"""

import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, List


@dataclass
class BrowserPath:
    """浏览器路径配置"""
    name: str
    cookie_file: str
    key_file: Optional[str] = None  # Chromium 的 Local State 或 Firefox 的 key4.db
    storage_name: Optional[str] = None  # 用于 Keychain/Secret Service
    is_chromium: bool = True


# 用户主目录
HOME = Path.home()

# macOS 路径
MACOS_PATHS = {
    "chrome": BrowserPath(
        name="Chrome",
        cookie_file=str(HOME / "Library/Application Support/Google/Chrome/Default/Cookies"),
        key_file=str(HOME / "Library/Application Support/Google/Chrome/Local State"),
        storage_name="Chrome",
        is_chromium=True
    ),
    "edge": BrowserPath(
        name="Edge",
        cookie_file=str(HOME / "Library/Application Support/Microsoft Edge/Default/Cookies"),
        key_file=str(HOME / "Library/Application Support/Microsoft Edge/Local State"),
        storage_name="Microsoft Edge",
        is_chromium=True
    ),
    "brave": BrowserPath(
        name="Brave",
        cookie_file=str(HOME / "Library/Application Support/BraveSoftware/Brave-Browser/Default/Cookies"),
        key_file=str(HOME / "Library/Application Support/BraveSoftware/Brave-Browser/Local State"),
        storage_name="Brave",
        is_chromium=True
    ),
    "opera": BrowserPath(
        name="Opera",
        cookie_file=str(HOME / "Library/Application Support/com.operasoftware.Opera/Default/Cookies"),
        key_file=str(HOME / "Library/Application Support/com.operasoftware.Opera/Local State"),
        storage_name="Opera",
        is_chromium=True
    ),
    "opera_gx": BrowserPath(
        name="Opera GX",
        cookie_file=str(HOME / "Library/Application Support/com.operasoftware.OperaGX/Default/Cookies"),
        key_file=str(HOME / "Library/Application Support/com.operasoftware.OperaGX/Local State"),
        storage_name="Opera",
        is_chromium=True
    ),
    "vivaldi": BrowserPath(
        name="Vivaldi",
        cookie_file=str(HOME / "Library/Application Support/Vivaldi/Default/Cookies"),
        key_file=str(HOME / "Library/Application Support/Vivaldi/Local State"),
        storage_name="Vivaldi",
        is_chromium=True
    ),
    "chromium": BrowserPath(
        name="Chromium",
        cookie_file=str(HOME / "Library/Application Support/Chromium/Default/Cookies"),
        key_file=str(HOME / "Library/Application Support/Chromium/Local State"),
        storage_name="Chromium",
        is_chromium=True
    ),
    "firefox": BrowserPath(
        name="Firefox",
        cookie_file="",  # Firefox 每个 profile 不同，需要动态查找
        key_file="",     # 动态查找 key4.db
        storage_name=None,
        is_chromium=False
    ),
}

# Windows 路径
WINDOWS_PATHS = {
    "chrome": BrowserPath(
        name="Chrome",
        cookie_file=str(HOME / "AppData/Local/Google/Chrome/User Data/Default/Cookies"),
        key_file=str(HOME / "AppData/Local/Google/Chrome/User Data/Local State"),
        storage_name=None,  # Windows 使用 DPAPI
        is_chromium=True
    ),
    "edge": BrowserPath(
        name="Edge",
        cookie_file=str(HOME / "AppData/Local/Microsoft/Edge/User Data/Default/Cookies"),
        key_file=str(HOME / "AppData/Local/Microsoft/Edge/User Data/Local State"),
        storage_name=None,
        is_chromium=True
    ),
    "brave": BrowserPath(
        name="Brave",
        cookie_file=str(HOME / "AppData/Local/BraveSoftware/Brave-Browser/User Data/Default/Cookies"),
        key_file=str(HOME / "AppData/Local/BraveSoftware/Brave-Browser/User Data/Local State"),
        storage_name=None,
        is_chromium=True
    ),
    "opera": BrowserPath(
        name="Opera",
        cookie_file=str(HOME / "AppData/Roaming/Opera Software/Opera Stable/Cookies"),
        key_file=str(HOME / "AppData/Roaming/Opera Software/Opera Stable/Local State"),
        storage_name=None,
        is_chromium=True
    ),
    "firefox": BrowserPath(
        name="Firefox",
        cookie_file="",
        key_file="",
        storage_name=None,
        is_chromium=False
    ),
}

# Linux 路径
LINUX_PATHS = {
    "chrome": BrowserPath(
        name="Chrome",
        cookie_file=str(HOME / ".config/google-chrome/Default/Cookies"),
        key_file=str(HOME / ".config/google-chrome/Local State"),
        storage_name="Chrome Safe Storage",
        is_chromium=True
    ),
    "edge": BrowserPath(
        name="Edge",
        cookie_file=str(HOME / ".config/microsoft-edge/Default/Cookies"),
        key_file=str(HOME / ".config/microsoft-edge/Local State"),
        storage_name="Chromium Safe Storage",
        is_chromium=True
    ),
    "brave": BrowserPath(
        name="Brave",
        cookie_file=str(HOME / ".config/BraveSoftware/Brave-Browser/Default/Cookies"),
        key_file=str(HOME / ".config/BraveSoftware/Brave-Browser/Local State"),
        storage_name="Brave Safe Storage",
        is_chromium=True
    ),
    "opera": BrowserPath(
        name="Opera",
        cookie_file=str(HOME / ".config/opera/Default/Cookies"),
        key_file=str(HOME / ".config/opera/Local State"),
        storage_name="Chromium Safe Storage",
        is_chromium=True
    ),
    "chromium": BrowserPath(
        name="Chromium",
        cookie_file=str(HOME / ".config/chromium/Default/Cookies"),
        key_file=str(HOME / ".config/chromium/Local State"),
        storage_name="Chromium Safe Storage",
        is_chromium=True
    ),
    "firefox": BrowserPath(
        name="Firefox",
        cookie_file="",
        key_file="",
        storage_name=None,
        is_chromium=False
    ),
}


def get_browser_paths() -> Dict[str, BrowserPath]:
    """获取当前平台的浏览器路径配置"""
    if sys.platform == 'darwin':
        return MACOS_PATHS
    elif sys.platform == 'win32':
        return WINDOWS_PATHS
    elif sys.platform == 'linux':
        return LINUX_PATHS
    else:
        raise NotImplementedError(f"不支持的平台: {sys.platform}")


def find_firefox_profiles() -> List[Dict[str, str]]:
    """
    查找 Firefox 配置文件
    Firefox 可以有多个 profile，每个都有独立的 cookies.sqlite 和 key4.db
    """
    profiles = []
    
    if sys.platform == 'darwin':
        base_path = HOME / "Library/Application Support/Firefox/Profiles"
    elif sys.platform == 'win32':
        base_path = HOME / "AppData/Roaming/Mozilla/Firefox/Profiles"
    elif sys.platform == 'linux':
        base_path = HOME / ".mozilla/firefox"
    else:
        return profiles
    
    if not base_path.exists():
        return profiles
    
    # 查找所有 profile 目录
    for profile_dir in base_path.iterdir():
        if profile_dir.is_dir() and '.' in profile_dir.name:
            cookies_file = profile_dir / "cookies.sqlite"
            key_file = profile_dir / "key4.db"
            
            if cookies_file.exists():
                profiles.append({
                    "name": profile_dir.name,
                    "cookies_file": str(cookies_file),
                    "key_file": str(key_file) if key_file.exists() else None,
                    "path": str(profile_dir)
                })
    
    return profiles


def get_browser_path(browser_name: str) -> Optional[BrowserPath]:
    """获取指定浏览器的路径配置"""
    paths = get_browser_paths()
    return paths.get(browser_name.lower())
