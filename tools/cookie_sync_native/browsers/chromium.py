"""
Chromium 系列浏览器 Cookie 提取
支持 Chrome, Edge, Brave, Opera, Vivaldi 等
"""

import base64
import json
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

from browsers.paths import get_browser_path


class ChromiumCookieExtractor:
    """Chromium Cookie 提取器"""
    
    def __init__(self, browser_name: str):
        self.browser_name = browser_name.lower()
        self.config = get_browser_path(self.browser_name)
        
        if not self.config:
            raise ValueError(f"不支持的浏览器: {browser_name}")
        
        if not self.config.is_chromium:
            raise ValueError(f"{browser_name} 不是 Chromium 内核浏览器")
        
        self._master_key: Optional[bytes] = None
    
    def _copy_db_to_temp(self, db_path: str) -> str:
        """
        将数据库复制到临时位置
        避免原数据库被锁定
        """
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_file.close()
        
        try:
            shutil.copy2(db_path, temp_file.name)
            return temp_file.name
        except Exception as e:
            Path(temp_file.name).unlink(missing_ok=True)
            raise
    
    def _get_master_key_windows(self) -> bytes:
        """Windows: 使用 DPAPI 解密 Local State 中的密钥"""
        from core.dpapi import dpapi_decrypt
        
        if not self.config.key_file:
            raise ValueError("未配置 key_file")
        
        local_state_path = Path(self.config.key_file)
        if not local_state_path.exists():
            raise FileNotFoundError(f"未找到 Local State 文件: {local_state_path}")
        
        with open(local_state_path, 'r', encoding='utf-8') as f:
            local_state = json.load(f)
        
        encrypted_key = local_state.get("os_crypt", {}).get("encrypted_key")
        if not encrypted_key:
            raise KeyError("Local State 中未找到 encrypted_key")
        
        # 解码 base64，移除前5字节 (DPAPI 前缀)
        key_data = base64.b64decode(encrypted_key)[5:]
        
        # 使用 DPAPI 解密
        return dpapi_decrypt(key_data)
    
    def _get_master_key_macos(self) -> bytes:
        """macOS: 从 Keychain 获取密码并派生密钥"""
        from core.keychain import get_chromium_key
        
        if not self.config.storage_name:
            raise ValueError("未配置 storage_name")
        
        return get_chromium_key(self.config.storage_name)
    
    def _get_master_key_linux(self) -> bytes:
        """Linux: 从 Secret Service 获取密码并派生密钥"""
        from core.secret_service import get_chromium_key
        
        if not self.config.storage_name:
            raise ValueError("未配置 storage_name")
        
        return get_chromium_key(self.config.storage_name)
    
    def get_master_key(self) -> bytes:
        """获取主密钥（平台无关）"""
        if self._master_key is not None:
            return self._master_key
        
        if sys.platform == 'win32':
            self._master_key = self._get_master_key_windows()
        elif sys.platform == 'darwin':
            self._master_key = self._get_master_key_macos()
        elif sys.platform == 'linux':
            self._master_key = self._get_master_key_linux()
        else:
            raise NotImplementedError(f"不支持的平台: {sys.platform}")
        
        return self._master_key
    
    def _decrypt_cookie(self, encrypted_value: bytes) -> str:
        """解密单个 Cookie 值"""
        if not encrypted_value:
            return ""
        
        if sys.platform == 'win32':
            from core.crypto import decrypt_chromium_cookie_windows
            key = self.get_master_key()
            return decrypt_chromium_cookie_windows(encrypted_value, key)
        
        elif sys.platform == 'darwin':
            from core.crypto import decrypt_chromium_cookie_macos
            key = self.get_master_key()
            return decrypt_chromium_cookie_macos(encrypted_value, key)
        
        elif sys.platform == 'linux':
            from core.crypto import decrypt_chromium_cookie_linux
            key = self.get_master_key()
            return decrypt_chromium_cookie_linux(encrypted_value, key)
        
        else:
            raise NotImplementedError(f"不支持的平台: {sys.platform}")
    
    def extract_cookies(self, domain_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        提取所有 Cookie
        
        Args:
            domain_filter: 只返回包含此字符串的域名的 Cookie
            
        Returns:
            Cookie 列表
        """
        cookie_file = Path(self.config.cookie_file)
        
        if not cookie_file.exists():
            raise FileNotFoundError(f"未找到 Cookie 文件: {cookie_file}")
        
        # 复制到临时位置
        temp_db = self._copy_db_to_temp(str(cookie_file))
        
        try:
            cookies = []
            
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            
            query = """
                SELECT host_key, name, value, encrypted_value, path,
                       expires_utc, is_secure, is_httponly, creation_utc, samesite
                FROM cookies
            """
            
            if domain_filter:
                query += " WHERE host_key LIKE ?"
                cursor.execute(query, (f"%{domain_filter}%",))
            else:
                cursor.execute(query)
            
            for row in cursor.fetchall():
                host_key, name, value, encrypted_value, path, \
                expires_utc, is_secure, is_httponly, creation_utc, samesite = row
                
                # 解密值
                try:
                    if encrypted_value:
                        decrypted_value = self._decrypt_cookie(encrypted_value)
                    else:
                        decrypted_value = value or ""
                except Exception as e:
                    # 解密失败时保留加密值（可能是其他加密方式）
                    decrypted_value = f"[解密失败: {e}]"
                
                # 转换时间戳 (Chromium 使用 microseconds since 1601)
                expire_date = None
                if expires_utc and expires_utc > 0:
                    expire_date = self._chrome_timestamp_to_datetime(expires_utc)
                
                create_date = None
                if creation_utc and creation_utc > 0:
                    create_date = self._chrome_timestamp_to_datetime(creation_utc)
                
                cookie = {
                    "host": host_key,
                    "name": name,
                    "value": decrypted_value,
                    "path": path,
                    "expires": expire_date.isoformat() if expire_date else None,
                    "secure": bool(is_secure),
                    "http_only": bool(is_httponly),
                    "same_site": self._parse_samesite(samesite),
                    "domain": host_key,
                }
                
                cookies.append(cookie)
            
            conn.close()
            return cookies
            
        finally:
            # 清理临时文件
            Path(temp_db).unlink(missing_ok=True)
    
    @staticmethod
    def _chrome_timestamp_to_timestamp(chrome_ts: int) -> float:
        """将 Chrome 时间戳（microseconds since 1601）转换为 Unix 时间戳"""
        # Chrome 时间戳起点: 1601-01-01 00:00:00 UTC
        # Unix 时间戳起点: 1970-01-01 00:00:00 UTC
        # 差值: 11644473600 秒
        return (chrome_ts / 1000000) - 11644473600
    
    @staticmethod
    def _chrome_timestamp_to_datetime(chrome_ts: int) -> datetime:
        """将 Chrome 时间戳转换为 datetime"""
        ts = ChromiumCookieExtractor._chrome_timestamp_to_timestamp(chrome_ts)
        return datetime.fromtimestamp(ts, tz=timezone.utc)

    @staticmethod
    def _parse_samesite(samesite: Optional[int]) -> Optional[str]:
        """
        解析 SameSite 属性

        Chromium samesite 值:
        - 0: None
        - 1: Lax
        - 2: Strict
        - None/其他：未设置

        Returns:
            "None" | "Lax" | "Strict" | None
        """
        if samesite is None:
            return None
        if samesite == 0:
            return "None"
        elif samesite == 1:
            return "Lax"
        elif samesite == 2:
            return "Strict"
        return None


def extract_all_chromium_cookies(domain_filter: Optional[str] = None) -> Dict[str, List[Dict]]:
    """
    从所有 Chromium 浏览器提取 Cookie
    
    Returns:
        {浏览器名称: Cookie列表}
    """
    from browsers.paths import get_browser_paths
    
    results = {}
    paths = get_browser_paths()
    
    for name, config in paths.items():
        if not config.is_chromium:
            continue
        
        try:
            extractor = ChromiumCookieExtractor(name)
            cookies = extractor.extract_cookies(domain_filter)
            results[config.name] = cookies
            print(f"✓ {config.name}: 提取了 {len(cookies)} 个 Cookie")
        except Exception as e:
            print(f"✗ {config.name}: {e}")
    
    return results
