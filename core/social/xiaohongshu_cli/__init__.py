"""
Xiaohongshu CLI Module - Integrated into Web-Rooter

This module provides complete xiaohongshu-cli functionality within the Web-Rooter ecosystem.
All original xhs_cli features are preserved and integrated with wr auth/cookie systems.

Usage:
    wr xhs search <keyword>
    wr xhs read <note_id_or_url>
    wr xhs comments <note_id_or_url>
    ... and 30+ more commands
"""

__version__ = "1.0.0-webrooter"

from .constants import (
    EDITH_HOST,
    CREATOR_HOST,
    HOME_URL,
    UPLOAD_HOST,
    CHROME_VERSION,
    USER_AGENT,
    SDK_VERSION,
    APP_ID,
    PLATFORM,
)

from .exceptions import (
    XhsApiError,
    NeedVerifyError,
    SessionExpiredError,
    IpBlockedError,
    SignatureError,
    UnsupportedOperationError,
    NoCookieError,
)

# Lazy import for XhsClient to avoid Crypto dependency at import time
def get_xhs_client(*args, **kwargs):
    """Get XhsClient instance (lazy import)."""
    from .client import XhsClient
    return XhsClient(*args, **kwargs)

# QR Login functionality
def qr_login(*args, **kwargs):
    """Perform QR code login (lazy import)."""
    from .qr_login import qrcode_login
    return qrcode_login(*args, **kwargs)

__all__ = [
    # Version
    "__version__",
    # Constants
    "EDITH_HOST",
    "CREATOR_HOST",
    "HOME_URL",
    "UPLOAD_HOST",
    "CHROME_VERSION",
    "USER_AGENT",
    "SDK_VERSION",
    "APP_ID",
    "PLATFORM",
    # Exceptions
    "XhsApiError",
    "NeedVerifyError",
    "SessionExpiredError",
    "IpBlockedError",
    "SignatureError",
    "UnsupportedOperationError",
    "NoCookieError",
    # Client factory
    "get_xhs_client",
    # QR Login
    "qr_login",
]
