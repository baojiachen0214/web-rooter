"""
Creator platform signing (XYW_ prefix) for creator.xiaohongshu.com

Algorithm: MD5(api + JSON(data)) → AES-128-CBC encrypt → XYW_ prefix
Much simpler than main API signing.

Ported from: ~/readers/redbook/src/lib/creator-signing.ts
"""

import base64
import hashlib
import json
import time

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

AES_KEY = b"7cc4adla5ay0701v"
AES_IV = b"4uzjr7mbsibcaldp"


def _aes_encrypt(data: str) -> str:
    """AES-128-CBC encrypt and return hex string."""
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    padded = pad(data.encode("utf-8"), AES.block_size)
    encrypted = cipher.encrypt(padded)
    return encrypted.hex()


def sign_creator(
    api: str,
    data: dict | None,
    a1: str,
) -> dict[str, str]:
    """
    Generate creator platform signature headers.

    Args:
        api: The API path, prefixed with "url=" (e.g., "url=/web_api/sns/v2/note")
        data: Request body data (None for GET requests)
        a1: The a1 cookie value

    Returns:
        Dict with x-s and x-t headers
    """
    content = api
    if data is not None:
        content += json.dumps(data, separators=(",", ":"), ensure_ascii=False)

    x1 = hashlib.md5(content.encode("utf-8")).hexdigest()
    x2 = "0|0|0|1|0|0|1|0|0|0|1|0|0|0|0|1|0|0|0"
    x3 = a1
    x4 = int(time.time() * 1000)

    plaintext = f"x1={x1};x2={x2};x3={x3};x4={x4};"
    payload = _aes_encrypt(base64.b64encode(plaintext.encode("utf-8")).decode("utf-8"))

    envelope = {
        "signSvn": "56",
        "signType": "x2",
        "appId": "ugc",
        "signVersion": "1",
        "payload": payload,
    }

    xs = "XYW_" + base64.b64encode(json.dumps(envelope, separators=(",", ":")).encode("utf-8")).decode("utf-8")

    return {
        "x-s": xs,
        "x-t": str(x4),
    }
