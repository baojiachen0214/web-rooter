"""
Firefox 加密算法实现
支持 Firefox 的 NSS 加密和 ASN1PBE 解密

参考:
- https://support.mozilla.org/en-US/kb/how-firefox-securely-saves-passwords
- HackBrowserData: crypto/asn1pbe.go
"""

import hashlib
import hmac
from typing import Tuple, Optional
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

from core.crypto import (
    CryptoError,
    aes_cbc_decrypt,
    des3_decrypt,
    pkcs7_unpad,
    padding_zero,
)


# ============================================================================
# ASN1 DER 标签定义
# ============================================================================

ASN1_SEQUENCE = 0x30
ASN1_OBJECT_IDENTIFIER = 0x06
ASN1_OCTET_STRING = 0x04
ASN1_INTEGER = 0x02


def parse_asn1_length(data: bytes, offset: int) -> Tuple[int, int]:
    """
    解析 ASN1 长度字段

    Returns:
        (length, new_offset)
    """
    if offset >= len(data):
        raise CryptoError("ASN1 解析失败：数据过短")

    first_byte = data[offset]
    offset += 1

    if first_byte < 0x80:
        # 短形式：长度直接在第一个字节
        return first_byte, offset
    elif first_byte == 0x80:
        # 不定长度（不应用于此场景）
        raise CryptoError("ASN1 解析失败：不支持不定长度")
    else:
        # 长形式：第一个字节的低 7 位表示长度字段的字节数
        num_length_bytes = first_byte & 0x7F
        if num_length_bytes > 4:
            raise CryptoError("ASN1 解析失败：长度字段过长")
        if offset + num_length_bytes > len(data):
            raise CryptoError("ASN1 解析失败：数据过短")

        length = 0
        for i in range(num_length_bytes):
            length = (length << 8) | data[offset + i]

        return length, offset + num_length_bytes


def parse_asn1_sequence(data: bytes, offset: int) -> Tuple[bytes, int]:
    """
    解析 ASN1 SEQUENCE

    Returns:
        (sequence_content, new_offset)
    """
    if offset >= len(data) or data[offset] != ASN1_SEQUENCE:
        raise CryptoError("ASN1 解析失败：期望 SEQUENCE")

    offset += 1
    length, offset = parse_asn1_length(data, offset)

    if offset + length > len(data):
        raise CryptoError("ASN1 解析失败：SEQUENCE 长度超出数据范围")

    return data[offset:offset + length], offset + length


def parse_asn1_octet_string(data: bytes, offset: int) -> Tuple[bytes, int]:
    """
    解析 ASN1 OCTET STRING

    Returns:
        (octet_string_content, new_offset)
    """
    if offset >= len(data) or data[offset] != ASN1_OCTET_STRING:
        raise CryptoError("ASN1 解析失败：期望 OCTET STRING")

    offset += 1
    length, offset = parse_asn1_length(data, offset)

    if offset + length > len(data):
        raise CryptoError("ASN1 解析失败：OCTET STRING 长度超出数据范围")

    return data[offset:offset + length], offset + length


def parse_asn1_oid(data: bytes, offset: int) -> Tuple[bytes, int]:
    """
    解析 ASN1 OBJECT IDENTIFIER

    Returns:
        (oid_bytes, new_offset)
    """
    if offset >= len(data) or data[offset] != ASN1_OBJECT_IDENTIFIER:
        raise CryptoError("ASN1 解析失败：期望 OID")

    offset += 1
    length, offset = parse_asn1_length(data, offset)

    if offset + length > len(data):
        raise CryptoError("ASN1 解析失败：OID 长度超出数据范围")

    return data[offset:offset + length], offset + length


def parse_asn1_integer(data: bytes, offset: int) -> Tuple[int, int]:
    """
    解析 ASN1 INTEGER

    Returns:
        (integer_value, new_offset)
    """
    if offset >= len(data) or data[offset] != ASN1_INTEGER:
        raise CryptoError("ASN1 解析失败：期望 INTEGER")

    offset += 1
    length, offset = parse_asn1_length(data, offset)

    if offset + length > len(data):
        raise CryptoError("ASN1 解析失败：INTEGER 长度超出数据范围")

    # 解析整数（大端）
    value = int.from_bytes(data[offset:offset + length], 'big', signed=data[offset] & 0x80 != 0)

    return value, offset + length


def skip_asn1_element(data: bytes, offset: int) -> int:
    """
    跳过 ASN1 元素

    Returns:
        new_offset
    """
    if offset >= len(data):
        raise CryptoError("ASN1 解析失败：数据过短")

    offset += 1  # 跳过标签
    length, offset = parse_asn1_length(data, offset)
    return offset + length


# ============================================================================
# NSS PBE (3DES-CBC)
# ============================================================================

class NSSPBE:
    """
    Firefox NSS PBE 实现

    ASN1 结构:
    SEQUENCE {
        SEQUENCE {
            OBJECT IDENTIFIER (algo)
            SEQUENCE {
                OCTET STRING (entrySalt)
                INTEGER (len)
            }
        }
        OCTET STRING (encrypted)
    }
    """

    def __init__(self, data: bytes):
        self.entry_salt = b''
        self.encrypted = b''
        self._parse(data)

    def _parse(self, data: bytes):
        """解析 ASN1 结构"""
        offset = 0

        # 解析外层 SEQUENCE
        seq_content, offset = parse_asn1_sequence(data, offset)

        # 在 SEQUENCE 内部，首先尝试解析 algo SEQUENCE
        inner_offset = 0

        # 第一个元素应该是 SEQUENCE (algo)
        if seq_content[inner_offset] == ASN1_SEQUENCE:
            algo_seq, inner_offset = parse_asn1_sequence(seq_content, inner_offset)

            # 解析 algo SEQUENCE 内部的 entrySalt
            # SEQUENCE { OID, SEQUENCE { entrySalt, len } }
            algo_offset = 0
            algo_oid, algo_offset = parse_asn1_oid(algo_seq, algo_offset)

            if algo_offset < len(algo_seq) and algo_seq[algo_offset] == ASN1_SEQUENCE:
                salt_seq, _ = parse_asn1_sequence(algo_seq, algo_offset)
                self.entry_salt, _ = parse_asn1_octet_string(salt_seq, 0)

        # 最后一个元素是 encrypted OCTET STRING
        if inner_offset < len(seq_content) and seq_content[inner_offset] == ASN1_OCTET_STRING:
            self.encrypted, _ = parse_asn1_octet_string(seq_content, inner_offset)
        elif offset < len(data) and data[offset] == ASN1_OCTET_STRING:
            self.encrypted, _ = parse_asn1_octet_string(data, offset)

    def derive_key_and_iv(self, global_salt: bytes) -> Tuple[bytes, bytes]:
        """
        派生密钥和 IV

        算法:
        1. sha1(global_salt) -> hash_prefix
        2. sha1(hash_prefix + entrySalt) -> composite_hash
        3. padded_entrySalt = entrySalt + (20 - len(entrySalt)) * \x00
        4. k1 = hmac(composite_hash, padded_entrySalt + entrySalt)
        5. k2 = hmac(composite_hash, k1 + entrySalt)
        6. key = k1 + k2 [:24]
        7. iv = key[-8:]
        """
        # sha1(global_salt)
        hash_prefix = hashlib.sha1(global_salt).digest()

        # sha1(hash_prefix + entrySalt)
        composite_hash = hashlib.sha1(hash_prefix + self.entry_salt).digest()

        # padded entrySalt (填充到 20 字节)
        padded_entry_salt = padding_zero(self.entry_salt, 20)

        # k1 = hmac(composite_hash, padded_entrySalt + entrySalt)
        k1 = hmac.new(composite_hash, padded_entry_salt + self.entry_salt, hashlib.sha1).digest()

        # k2 = hmac(composite_hash, k1 + entrySalt)
        k2 = hmac.new(composite_hash, k1 + self.entry_salt, hashlib.sha1).digest()

        # key = k1 + k2, 取前 24 字节
        key = (k1 + k2)[:24]

        # iv = key 最后 8 字节
        iv = key[-8:]

        return key, iv

    def decrypt(self, global_salt: bytes) -> bytes:
        """使用 3DES-CBC 解密"""
        key, iv = self.derive_key_and_iv(global_salt)
        return des3_decrypt(key, iv, self.encrypted)


# ============================================================================
# Meta PBE (AES-128-CBC)
# ============================================================================

class MetaPBE:
    """
    Firefox Meta PBE 实现 (用于加密 master key)

    ASN1 结构 (更复杂):
    SEQUENCE {
        SEQUENCE {
            OID (pbes2)
            SEQUENCE {
                SEQUENCE {
                    OID (pbkdf2)
                    SEQUENCE {
                        OCTET STRING (salt)
                        INTEGER (iterations)
                        INTEGER (keyLength)
                        SEQUENCE {
                            OID (sha256)
                        }
                    }
                }
                SEQUENCE {
                    OID (aes128-cbc)
                    OCTET STRING (iv)
                }
            }
        }
        OCTET STRING (encrypted)
    }
    """

    def __init__(self, data: bytes):
        self.salt = b''
        self.iterations = 1
        self.key_size = 32
        self.iv = b''
        self.encrypted = b''
        self._parse(data)

    def _parse(self, data: bytes):
        """解析 ASN1 结构"""
        offset = 0

        # 解析外层 SEQUENCE
        seq_content, _ = parse_asn1_sequence(data, offset)

        # 内部结构偏移
        inner_offset = 0

        # 跳过外层 OID (pbes2)
        if seq_content[inner_offset] == ASN1_OBJECT_IDENTIFIER:
            _, inner_offset = parse_asn1_oid(seq_content, inner_offset)

        # 解析参数 SEQUENCE
        if inner_offset < len(seq_content) and seq_content[inner_offset] == ASN1_SEQUENCE:
            params_seq, inner_offset = parse_asn1_sequence(seq_content, inner_offset)

            # 解析 pbkdf2 参数
            params_offset = 0
            if params_seq[params_offset] == ASN1_SEQUENCE:
                pbkdf2_seq, params_offset = parse_asn1_sequence(params_seq, params_offset)

                # 跳过 pbkdf2 OID
                pbkdf2_offset = 0
                if pbkdf2_seq[pbkdf2_offset] == ASN1_OBJECT_IDENTIFIER:
                    _, pbkdf2_offset = parse_asn1_oid(pbkdf2_seq, pbkdf2_offset)

                # 解析 pbkdf2 参数 SEQUENCE
                if pbkdf2_offset < len(pbkdf2_seq) and pbkdf2_seq[pbkdf2_offset] == ASN1_SEQUENCE:
                    salt_seq, pbkdf2_offset = parse_asn1_sequence(pbkdf2_seq, pbkdf2_offset)

                    # salt (OCTET STRING)
                    if salt_seq[0] == ASN1_OCTET_STRING:
                        self.salt, pbkdf2_offset = parse_asn1_octet_string(salt_seq, 0)

                    # iterations (INTEGER)
                    if pbkdf2_offset < len(salt_seq) and salt_seq[pbkdf2_offset] == ASN1_INTEGER:
                        self.iterations, pbkdf2_offset = parse_asn1_integer(salt_seq, pbkdf2_offset)

                    # keyLength (INTEGER)
                    if pbkdf2_offset < len(salt_seq) and salt_seq[pbkdf2_offset] == ASN1_INTEGER:
                        self.key_size, _ = parse_asn1_integer(salt_seq, pbkdf2_offset)

            # 解析 AES 参数
            if params_offset < len(params_seq) and params_seq[params_offset] == ASN1_SEQUENCE:
                aes_seq, _ = parse_asn1_sequence(params_seq, params_offset)

                # 跳过 AES OID
                aes_offset = 0
                if aes_seq[aes_offset] == ASN1_OBJECT_IDENTIFIER:
                    _, aes_offset = parse_asn1_oid(aes_seq, aes_offset)

                # IV (OCTET STRING)
                if aes_offset < len(aes_seq) and aes_seq[aes_offset] == ASN1_OCTET_STRING:
                    self.iv, _ = parse_asn1_octet_string(aes_seq, aes_offset)

        # encrypted (OCTET STRING) - 在最后的 offset
        if inner_offset < len(seq_content) and seq_content[inner_offset] == ASN1_OCTET_STRING:
            self.encrypted, _ = parse_asn1_octet_string(seq_content, inner_offset)

    def decrypt(self, global_salt: bytes) -> bytes:
        """
        解密

        1. key = PBKDF2(sha1(global_salt), salt, iterations, key_size, sha256)
        2. plaintext = AES-CBC-128(key, iv, encrypted)
        """
        password = hashlib.sha1(global_salt).digest()

        # PBKDF2 with SHA256
        from core.crypto import pbkdf2
        key = pbkdf2(password, self.salt, self.iterations, self.key_size, hashlib.sha256)

        return aes_cbc_decrypt(key, self.iv, self.encrypted)


# ============================================================================
# Login PBE (用于加密的 username/password)
# ============================================================================

class LoginPBE:
    """
    Firefox Login PBE 实现

    ASN1 结构:
    OCTET STRING (cipherText)
    SEQUENCE {
        OBJECT IDENTIFIER
        OCTET STRING (iv)
    }
    OCTET STRING (encrypted)
    """

    def __init__(self, data: bytes):
        self.ciphertext = b''
        self.iv = b''
        self.encrypted = b''
        self._parse(data)

    def _parse(self, data: bytes):
        """解析 ASN1 结构"""
        offset = 0

        # cipherText (OCTET STRING)
        if offset < len(data) and data[offset] == ASN1_OCTET_STRING:
            self.ciphertext, offset = parse_asn1_octet_string(data, offset)

        # SEQUENCE { OID, IV }
        if offset < len(data) and data[offset] == ASN1_SEQUENCE:
            seq_content, offset = parse_asn1_sequence(data, offset)
            seq_offset = 0

            # 跳过 OID
            if seq_content[seq_offset] == ASN1_OBJECT_IDENTIFIER:
                _, seq_offset = parse_asn1_oid(seq_content, seq_offset)

            # IV (OCTET STRING)
            if seq_offset < len(seq_content) and seq_content[seq_offset] == ASN1_OCTET_STRING:
                self.iv, _ = parse_asn1_octet_string(seq_content, seq_offset)

        # encrypted (OCTET STRING)
        if offset < len(data) and data[offset] == ASN1_OCTET_STRING:
            self.encrypted, _ = parse_asn1_octet_string(data, offset)

    def decrypt(self, global_salt: bytes) -> bytes:
        """
        解密 Login 数据

        IV 长度决定加密算法:
        - 8 字节: 3DES-CBC (旧版 Firefox)
        - 16 字节：AES-CBC (Firefox 144+)
        """
        if len(self.iv) == 8:
            # 3DES-CBC
            key = global_salt[:24] if len(global_salt) >= 24 else global_salt
            return des3_decrypt(key, self.iv, self.encrypted)
        elif len(self.iv) == 16:
            # AES-CBC (Firefox 144+ 使用 32 字节密钥)
            key = global_salt
            return aes_cbc_decrypt(key, self.iv, self.encrypted)
        else:
            raise CryptoError(f"不支持的 IV 长度：{len(self.iv)}")


# ============================================================================
# PBE 工厂函数
# ============================================================================

def new_asn1_pbe(data: bytes):
    """
    从 ASN1 数据创建 PBE 实例

    尝试按顺序解析:
    1. NSS PBE
    2. Meta PBE
    3. Login PBE
    """
    # 尝试 NSS PBE
    try:
        return NSSPBE(data)
    except Exception:
        pass

    # 尝试 Meta PBE
    try:
        return MetaPBE(data)
    except Exception:
        pass

    # 尝试 Login PBE
    try:
        return LoginPBE(data)
    except Exception:
        pass

    raise CryptoError("无法解析 ASN1 PBE 数据")


# ============================================================================
# Firefox key4.db 解密辅助函数
# ============================================================================

def decrypt_with_pbe(pbe_data: bytes, global_salt: bytes) -> Optional[bytes]:
    """
    通用 PBE 解密函数

    Args:
        pbe_data: ASN1 编码的 PBE 数据
        global_salt: 全局盐

    Returns:
        解密后的数据，失败返回 None
    """
    try:
        pbe = new_asn1_pbe(pbe_data)
        return pbe.decrypt(global_salt)
    except Exception as e:
        return None


def verify_master_key(master_key: bytes, encrypted_login: bytes) -> bool:
    """
    验证 master key 是否能正确解密 login 数据

    Args:
        master_key: 主密钥
        encrypted_login: 加密的 login 数据 (base64 解码后的 username 或 password)

    Returns:
        True 如果解密成功
    """
    try:
        pbe = new_asn1_pbe(encrypted_login)
        pbe.decrypt(master_key)
        return True
    except Exception:
        return False
