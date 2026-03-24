"""
Linux Secret Service (D-Bus) 访问
用于获取 Chromium 在 Linux 上的存储密码
"""

import sys

if sys.platform != 'linux':
    def get_chromium_password(storage_name: str = "Chrome") -> str:
        raise NotImplementedError("Secret Service 仅在 Linux 上可用")
    
    def get_chromium_key(storage_name: str = "Chrome") -> bytes:
        raise NotImplementedError("Secret Service 仅在 Linux 上可用")

else:
    def get_chromium_password(storage_name: str = "Chrome") -> str:
        """
        从 Secret Service 获取 Chromium 密码
        尝试使用 secret-tool 或直接访问 D-Bus
        """
        # 首先尝试 secret-tool（libsecret 的命令行工具）
        try:
            import subprocess
            result = subprocess.run(
                ["secret-tool", "lookup", "application", storage_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # 尝试使用 dbus-python
        try:
            import dbus
            return _get_password_via_dbus(storage_name)
        except ImportError:
            pass
        
        # 返回默认值
        return "peanuts"
    
    def _get_password_via_dbus(storage_name: str) -> str:
        """通过 D-Bus 访问 Secret Service"""
        try:
            import dbus
            
            bus = dbus.SessionBus()
            
            # 获取 Secret Service
            service_obj = bus.get_object(
                "org.freedesktop.secrets",
                "/org/freedesktop/secrets"
            )
            service_iface = dbus.Interface(service_obj, "org.freedesktop.Secret.Service")
            
            # 打开会话
            session = service_iface.OpenSession("plain", "")[1]
            
            # 搜索项目
            attrs = {"application": storage_name}
            items = service_iface.SearchItems(attrs)[0]  # unlocked items
            
            if items:
                # 获取第一个项目的秘密
                item_path = items[0]
                item_obj = bus.get_object("org.freedesktop.secrets", item_path)
                item_iface = dbus.Interface(item_obj, "org.freedesktop.Secret.Item")
                
                secret = item_iface.GetSecret(session)
                password = bytes(secret[2]).decode('utf-8')
                
                # 关闭会话
                service_iface.CloseSession(session)
                
                return password
            
            # 关闭会话
            service_iface.CloseSession(session)
            
        except Exception:
            pass
        
        return "peanuts"
    
    def get_chromium_key(storage_name: str = "Chrome") -> bytes:
        """
        获取 Chromium 主密钥
        流程: 从 Secret Service 获取密码 -> PBKDF2 派生密钥
        """
        from core.crypto import derive_chromium_key_linux
        
        password = get_chromium_password(storage_name)
        return derive_chromium_key_linux(password)
