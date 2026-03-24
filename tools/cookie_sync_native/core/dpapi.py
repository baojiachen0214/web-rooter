"""
Windows DPAPI (Data Protection API) 解密
"""

import sys

if sys.platform != 'win32':
    # 在非 Windows 平台提供占位实现
    def dpapi_decrypt(data: bytes) -> bytes:
        raise NotImplementedError("DPAPI 仅在 Windows 上可用")
    
    def dpapi_encrypt(data: bytes) -> bytes:
        raise NotImplementedError("DPAPI 仅在 Windows 上可用")

else:
    import ctypes
    from ctypes import wintypes
    
    # Windows API 定义
    CRYPTPROTECT_UI_FORBIDDEN = 0x01
    
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", wintypes.LPBYTE)
        ]
    
    def dpapi_decrypt(data: bytes) -> bytes:
        """
        使用 Windows DPAPI 解密数据
        """
        if not data:
            return b""
        
        # 加载 Crypt32.dll
        crypt32 = ctypes.windll.crypt32
        
        # 准备输入数据结构
        input_blob = DATA_BLOB()
        input_blob.cbData = len(data)
        input_blob.pbData = ctypes.cast(ctypes.create_string_buffer(data), wintypes.LPBYTE)
        
        # 准备输出数据结构
        output_blob = DATA_BLOB()
        
        # 调用 CryptUnprotectData
        result = crypt32.CryptUnprotectData(
            ctypes.byref(input_blob),
            None,  # ppszDataDescr
            None,  # pOptionalEntropy
            None,  # pvReserved
            None,  # pPromptStruct
            CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob)
        )
        
        if not result:
            raise RuntimeError("CryptUnprotectData 失败")
        
        # 提取解密后的数据
        decrypted = ctypes.string_at(output_blob.pbData, output_blob.cbData)
        
        # 释放内存
        kernel32 = ctypes.windll.kernel32
        kernel32.LocalFree(output_blob.pbData)
        
        return decrypted
    
    def dpapi_encrypt(data: bytes) -> bytes:
        """
        使用 Windows DPAPI 加密数据
        """
        if not data:
            return b""
        
        crypt32 = ctypes.windll.crypt32
        
        input_blob = DATA_BLOB()
        input_blob.cbData = len(data)
        input_blob.pbData = ctypes.cast(ctypes.create_string_buffer(data), wintypes.LPBYTE)
        
        output_blob = DATA_BLOB()
        
        result = crypt32.CryptProtectData(
            ctypes.byref(input_blob),
            None,
            None,
            None,
            None,
            CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob)
        )
        
        if not result:
            raise RuntimeError("CryptProtectData 失败")
        
        encrypted = ctypes.string_at(output_blob.pbData, output_blob.cbData)
        
        kernel32 = ctypes.windll.kernel32
        kernel32.LocalFree(output_blob.pbData)
        
        return encrypted
