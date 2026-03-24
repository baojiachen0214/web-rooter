"""
macOS Keychain 访问
获取 Chromium 存储的密码
"""

import subprocess
import sys

if sys.platform != 'darwin':
    def get_chromium_password(storage_name: str = "Chrome") -> str:
        raise NotImplementedError("Keychain 访问仅在 macOS 上可用")
else:
    def get_chromium_password(storage_name: str = "Chrome") -> str:
        """
        从 macOS Keychain 获取 Chromium 密码
        执行: security find-generic-password -wa 'Chrome'
        """
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-wa", storage_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                # 检查是否是 "未找到" 错误
                if "could not be found" in result.stderr.lower():
                    raise KeyError(f"在 Keychain 中未找到 {storage_name} 的密码")
                raise RuntimeError(f"security 命令失败: {result.stderr}")
            
            password = result.stdout.strip()
            if not password:
                raise ValueError("获取到的密码为空")
            
            return password
            
        except FileNotFoundError:
            raise RuntimeError("未找到 security 命令，请确保在 macOS 上运行")
        except subprocess.TimeoutExpired:
            raise RuntimeError("获取密码超时")


def get_chromium_key(storage_name: str = "Chrome") -> bytes:
    """
    获取 Chromium 主密钥
    流程: 从 Keychain 获取密码 -> PBKDF2 派生密钥
    """
    from core.crypto import derive_chromium_key_macos
    
    password = get_chromium_password(storage_name)
    return derive_chromium_key_macos(password)
