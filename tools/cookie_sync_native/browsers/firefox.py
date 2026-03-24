"""
Firefox Cookie 提取
支持：
- 明文 Cookie 直接读取
- 加密 Cookie 使用 NSS 解密 (key4.db)

注意：Firefox 的 Cookie 通常是未加密的（明文存储）
只有密码等敏感数据使用 NSS 加密
"""

import base64
import json
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from browsers.paths import find_firefox_profiles


class FirefoxCookieExtractor:
    """Firefox Cookie 提取器"""

    def __init__(self, profile_path: Optional[str] = None):
        """
        Args:
            profile_path: 指定 profile 路径，None 则自动查找第一个
        """
        if profile_path:
            self.profile_path = Path(profile_path)
            self.profile_name = self.profile_path.name
        else:
            profiles = find_firefox_profiles()
            if not profiles:
                raise FileNotFoundError("未找到 Firefox 配置文件")

            self.profile_path = Path(profiles[0]["path"])
            self.profile_name = profiles[0]["name"]

        self.cookies_file = self.profile_path / "cookies.sqlite"
        self.key4_db_file = self.profile_path / "key4.db"
        self.logins_file = self.profile_path / "logins.json"

        self._master_key: Optional[bytes] = None

    def _copy_db_to_temp(self, db_path: str) -> str:
        """将数据库复制到临时位置"""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_file.close()

        try:
            shutil.copy2(db_path, temp_file.name)
            return temp_file.name
        except Exception as e:
            Path(temp_file.name).unlink(missing_ok=True)
            raise

    def _get_master_key(self) -> Optional[bytes]:
        """
        从 key4.db 获取 Firefox 主密钥

        参考：HackBrowserData - browser/firefox/firefox.go

        Returns:
            主密钥，如果不可用返回 None
        """
        if not self.key4_db_file.exists():
            return None

        try:
            from core.firefox_crypto import (
                new_asn1_pbe,
                MetaPBE,
                NSSPBE,
                verify_master_key,
            )

            # 复制 key4.db 到临时位置
            temp_key_db = self._copy_db_to_temp(str(self.key4_db_file))

            try:
                conn = sqlite3.connect(temp_key_db)
                cursor = conn.cursor()

                # 查询 metaData 表
                cursor.execute("SELECT item1, item2 FROM metaData WHERE id = 'password'")
                row = cursor.fetchone()

                if not row:
                    conn.close()
                    return None

                meta_item1, meta_item2 = row[0], row[1]

                # 查询 nssPrivate 表
                cursor.execute("SELECT a11, a102 FROM nssPrivate")
                rows = cursor.fetchall()

                conn.close()

                if not rows:
                    return None

                # 尝试所有候选密钥
                for a11, a102 in rows:
                    try:
                        # 解析 metaItem2 获取 salt 和参数
                        meta_pbe = new_asn1_pbe(meta_item2)

                        if not isinstance(meta_pbe, MetaPBE):
                            continue

                        # 使用 global salt (metaItem1) 解密 metaItem2 获取 flag
                        flag = meta_pbe.decrypt(meta_item1)

                        # 验证 password-check 标志
                        if b"password-check" not in flag:
                            continue

                        # 验证 a102 (应该是固定的 16 字节)
                        expected_a102 = bytes([
                            248, 0, 0, 0, 0, 0, 0, 0,
                            0, 0, 0, 0, 0, 0, 0, 1
                        ])

                        if a102 != expected_a102:
                            continue

                        # 使用 NSS PBE 解密 a11 获取最终密钥
                        nss_pbe = new_asn1_pbe(a11)

                        if not isinstance(nss_pbe, NSSPBE):
                            continue

                        finally_key = nss_pbe.decrypt(meta_item1)

                        # 验证密钥是否能解密 login 数据
                        if self._verify_key_with_logins(finally_key):
                            self._master_key = finally_key
                            return finally_key

                    except Exception:
                        continue

                return None

            finally:
                Path(temp_key_db).unlink(missing_ok=True)

        except Exception:
            return None

    def _verify_key_with_logins(self, master_key: bytes) -> bool:
        """
        验证主密钥是否能解密 logins 数据
        """
        if not self.logins_file.exists():
            # 没有 logins 文件，假设密钥有效
            return True

        try:
            from core.firefox_crypto import new_asn1_pbe

            with open(self.logins_file, 'r', encoding='utf-8') as f:
                logins_data = json.load(f)

            logins = logins_data.get("logins", [])

            for login in logins[:3]:  # 最多检查 3 个
                encrypted_username = login.get("encryptedUsername")
                if not encrypted_username:
                    continue

                try:
                    encrypted_data = base64.b64decode(encrypted_username)
                    pbe = new_asn1_pbe(encrypted_data)
                    pbe.decrypt(master_key)
                    return True  # 解密成功，密钥有效
                except Exception:
                    continue

            return False

        except Exception:
            return True  # 无法验证，假设有效

    def _decrypt_cookie_value(self, encrypted_value: bytes) -> str:
        """
        解密加密的 Cookie 值

        Firefox Cookie 通常未加密，但某些情况下可能加密
        """
        if not encrypted_value:
            return ""

        # 尝试使用主密钥解密
        if self._master_key:
            try:
                from core.firefox_crypto import new_asn1_pbe

                pbe = new_asn1_pbe(encrypted_value)
                decrypted = pbe.decrypt(self._master_key)
                return decrypted.decode('utf-8', errors='replace')
            except Exception:
                pass

        # 无法解密，返回原始值（可能是明文）
        return encrypted_value.decode('utf-8', errors='replace')

    def extract_cookies(self, domain_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        提取 Cookie

        Firefox 的 Cookie 通常是明文的，但某些情况下可能加密
        """
        if not self.cookies_file.exists():
            raise FileNotFoundError(f"未找到 Cookie 文件：{self.cookies_file}")

        # 尝试获取主密钥（用于解密可能的加密 Cookie）
        self._get_master_key()

        temp_db = self._copy_db_to_temp(str(self.cookies_file))

        try:
            cookies = []

            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()

            query = """
                SELECT host, name, value, path, expiry, isSecure, isHttpOnly, creationTime
                FROM moz_cookies
            """

            if domain_filter:
                query += " WHERE host LIKE ?"
                cursor.execute(query, (f"%{domain_filter}%",))
            else:
                cursor.execute(query)

            for row in cursor.fetchall():
                host, name, value, path, expiry, is_secure, is_http_only, creation_time = row

                # Firefox 时间戳：
                # - expiry: 秒 (Unix timestamp)
                # - creationTime: 微秒 (PRTime)
                expire_date = None
                if expiry:
                    expire_date = datetime.fromtimestamp(expiry, tz=timezone.utc)

                create_date = None
                if creation_time:
                    # creationTime 是微秒，转换为秒
                    create_date = datetime.fromtimestamp(creation_time / 1000000, tz=timezone.utc)

                # Cookie 值通常是明文，但某些情况下可能加密
                # 注意：现代 Firefox 的 Cookie 是明文的，不需要解密
                cookie_value = value or ""

                cookie = {
                    "host": host,
                    "name": name,
                    "value": cookie_value,
                    "path": path,
                    "expires": expire_date.isoformat() if expire_date else None,
                    "secure": bool(is_secure),
                    "http_only": bool(is_http_only),
                    "domain": host,
                }

                cookies.append(cookie)

            conn.close()
            return cookies

        finally:
            Path(temp_db).unlink(missing_ok=True)


def extract_all_firefox_cookies(domain_filter: Optional[str] = None) -> Dict[str, List[Dict]]:
    """
    从所有 Firefox 配置文件提取 Cookie
    """
    results = {}
    profiles = find_firefox_profiles()

    for profile in profiles:
        try:
            extractor = FirefoxCookieExtractor(profile["path"])
            cookies = extractor.extract_cookies(domain_filter)
            results[f"Firefox ({profile['name']})"] = cookies
            print(f"✓ Firefox ({profile['name']}): 提取了 {len(cookies)} 个 Cookie")
        except Exception as e:
            print(f"✗ Firefox ({profile['name']}): {e}")

    return results
