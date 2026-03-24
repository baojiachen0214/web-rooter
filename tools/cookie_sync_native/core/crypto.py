"""
浏览器数据解密模块
实现 Chromium 和 Firefox 的加密算法
"""

import hashlib
import hmac
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


class CryptoError(Exception):
    """加密操作错误"""
    pass


def aes_cbc_decrypt(key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    """
    AES-CBC 解密
    支持 AES-128/192/256（自动根据密钥长度选择）
    """
    if len(ciphertext) % 16 != 0:
        raise CryptoError("密文长度必须是16的倍数")
    
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    padded_data = decryptor.update(ciphertext) + decryptor.finalize()
    
    # PKCS5/PKCS7 去填充
    return pkcs7_unpad(padded_data)


def aes_gcm_decrypt(key: bytes, nonce: bytes, ciphertext: bytes, tag: bytes) -> bytes:
    """
    AES-GCM 解密
    Chromium 80+ 在 Windows 上使用

    Args:
        key: 解密密钥 (16/24/32 字节)
        nonce: 随机数 (12 字节)
        ciphertext: 密文
        tag: authentication tag (16 字节)
    """
    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag), backend=default_backend())
    decryptor = cipher.decryptor()
    return decryptor.update(ciphertext) + decryptor.finalize()


def des3_decrypt(key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    """
    3DES-CBC 解密
    Firefox 旧版本使用
    """
    if len(ciphertext) % 8 != 0:
        raise CryptoError("密文长度必须是8的倍数")
    
    cipher = Cipher(algorithms.TripleDES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    padded_data = decryptor.update(ciphertext) + decryptor.finalize()
    
    return pkcs7_unpad(padded_data, block_size=8)


def pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    """PKCS7 填充"""
    padding_len = block_size - (len(data) % block_size)
    padding = bytes([padding_len] * padding_len)
    return data + padding


def padding_zero(src: bytes, length: int) -> bytes:
    """
    零填充（用于 Firefox NSS PBE）
    如果源数据长度不足，用 0x00 填充到指定长度
    """
    padding = length - len(src)
    if padding <= 0:
        return src
    return src + bytes(padding)


def pkcs7_unpad(data: bytes, block_size: int = 16) -> bytes:
    """PKCS7 去填充"""
    if not data:
        raise CryptoError("数据不能为空")
    
    padding_len = data[-1]
    if padding_len < 1 or padding_len > block_size:
        raise CryptoError(f"无效的填充长度: {padding_len}")
    
    if padding_len > len(data):
        raise CryptoError("填充长度超过数据长度")
    
    # 验证填充内容
    for i in range(1, padding_len + 1):
        if data[-i] != padding_len:
            raise CryptoError("填充内容不一致")
    
    return data[:-padding_len]


def pbkdf2(password: bytes, salt: bytes, iterations: int, key_len: int, 
           hash_func=hashlib.sha1) -> bytes:
    """
    PBKDF2 密钥派生
    符合 RFC 2898
    """
    prf = hmac.new(password, digestmod=hash_func)
    hash_len = prf.digest_size
    num_blocks = (key_len + hash_len - 1) // hash_len
    
    result = b''
    
    for block in range(1, num_blocks + 1):
        # U_1 = PRF(password, salt || block_num)
        prf_block = hmac.new(password, digestmod=hash_func)
        prf_block.update(salt)
        prf_block.update(block.to_bytes(4, 'big'))
        u = prf_block.digest()
        block_result = u
        
        # U_2 到 U_iter
        for _ in range(1, iterations):
            prf_iter = hmac.new(password, digestmod=hash_func)
            prf_iter.update(u)
            u = prf_iter.digest()
            # XOR
            block_result = bytes(a ^ b for a, b in zip(block_result, u))
        
        result += block_result
    
    return result[:key_len]


def derive_chromium_key_macos(password: str) -> bytes:
    """
    macOS 上派生 Chromium 密钥
    PBKDF2(password, salt="saltysalt", iterations=1003, keylen=16, hash=SHA1)
    """
    salt = b"saltysalt"
    return pbkdf2(password.encode('utf-8'), salt, 1003, 16, hashlib.sha1)


def derive_chromium_key_linux(password: str) -> bytes:
    """
    Linux 上派生 Chromium 密钥
    PBKDF2(password, salt="saltysalt", iterations=1, keylen=16, hash=SHA1)
    """
    salt = b"saltysalt"
    return pbkdf2(password.encode('utf-8'), salt, 1, 16, hashlib.sha1)


def decrypt_chromium_cookie_macos(encrypted_value: bytes, key: bytes) -> str:
    """
    解密 macOS 上的 Chromium Cookie
    格式: v10 + ciphertext
    加密: AES-CBC，固定 IV
    """
    if not encrypted_value:
        return ""
    
    # 检查前缀
    if encrypted_value[:3] != b'v10':
        raise CryptoError(f"未知的加密格式: {encrypted_value[:3]}")
    
    ciphertext = encrypted_value[3:]
    
    # macOS 使用固定 IV (16个ASCII 32 = 空格)
    iv = b' ' * 16
    
    decrypted = aes_cbc_decrypt(key, iv, ciphertext)
    return decrypted.decode('utf-8', errors='replace')


def decrypt_chromium_cookie_windows(encrypted_value: bytes, key: bytes) -> str:
    """
    解密 Windows 上的 Chromium Cookie
    格式: v10 + nonce(12字节) + ciphertext + tag(16字节)
    加密: AES-GCM
    """
    if not encrypted_value:
        return ""
    
    if encrypted_value[:3] != b'v10':
        # 旧版本可能使用 DPAPI，尝试直接使用
        try:
            from core.dpapi import dpapi_decrypt
            return dpapi_decrypt(encrypted_value).decode('utf-8', errors='replace')
        except:
            raise CryptoError(f"未知的加密格式: {encrypted_value[:3]}")
    
    # v10 格式：v10 + nonce(12) + ciphertext + tag(16)
    payload = encrypted_value[3:]

    if len(payload) < 28:  # 至少需要 nonce(12) + tag(16)
        raise CryptoError(f"密文长度过短：{len(payload)} 字节")

    nonce = payload[:12]
    tag = payload[-16:]  # tag 在最后 16 字节
    ciphertext = payload[12:-16]  # 中间部分是密文

    decrypted = aes_gcm_decrypt(key, nonce, ciphertext, tag)
    return decrypted.decode('utf-8', errors='replace')



def decrypt_chromium_cookie_linux(encrypted_value: bytes, key: bytes) -> str:
    """
    解密 Linux 上的 Chromium Cookie
    与 macOS 相同: v10 + ciphertext，AES-CBC
    """
    return decrypt_chromium_cookie_macos(encrypted_value, key)
