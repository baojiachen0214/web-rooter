"""
Xiaohongshu API Signing Module

Based on xhshow library for generating X-S, X-T, and X-S-Common headers
required to access xiaohongshu's private API (edith.xiaohongshu.com).

This module is a thin wrapper around xhshow, configured for macOS/Chrome.
Reference: xiaohongshu-cli implementation
"""

from typing import Any

# xhshow library imports
try:
    from xhshow import CryptoConfig, SessionManager, Xhshow
    from xhshow.utils.url_utils import extract_uri
except ImportError:
    raise ImportError(
        "xhshow library is required for xiaohongshu API signing. "
        "Install with: pip install xhshow>=0.1.9"
    )

# =============================================================================
# Constants (from xiaohongshu-cli)
# =============================================================================

EDITH_HOST = "https://edith.xiaohongshu.com"
CREATOR_HOST = "https://creator.xiaohongshu.com"
HOME_URL = "https://www.xiaohongshu.com"
UPLOAD_HOST = "https://ros-upload.xiaohongshu.com"

CHROME_VERSION = "145"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    f"Chrome/{CHROME_VERSION}.0.0.0 Safari/537.36"
)

SDK_VERSION = "4.2.6"
APP_ID = "xhs-pc-web"
PLATFORM = "macOS"

# =============================================================================
# Global Signing Instance (lazy initialization)
# =============================================================================

_config: CryptoConfig | None = None
_xhshow: Xhshow | None = None
_session: SessionManager | None = None


def _init_signing() -> None:
    """Initialize the global signing instance with default config."""
    global _config, _xhshow, _session
    
    if _config is not None:
        return
    
    _config = CryptoConfig().with_overrides(
        PUBLIC_USERAGENT=USER_AGENT,
        SIGNATURE_DATA_TEMPLATE={
            "x0": SDK_VERSION,
            "x1": APP_ID,
            "x2": PLATFORM,
            "x3": f"Chrome/{CHROME_VERSION}.0.0.0",
            "x4": CHROME_VERSION,
            "x5": "",
            "x6": EDITH_HOST,
            "x7": HOME_URL,
            "x8": CHROME_VERSION,
            "x9": "Google",
            "x10": "104",
        },
        SIGNATURE_XSCOMMON_TEMPLATE={
            "s0": 5,
            "x0": "1",
            "x1": "3.7.8-2",
            "x2": PLATFORM,
            "x3": "xhs-pc",
            "x4": "zh-Hans",
            "x5": "1482",
            "x6": CHROME_VERSION,
            "x7": HOME_URL,
            "x8": EDITH_HOST,
            "x9": SDK_VERSION,
        },
    )
    _xhshow = Xhshow(_config)
    _session = SessionManager()


def sign_main_api(
    method: str,
    uri: str,
    cookies: dict[str, str],
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, str]:
    """
    Generate signed headers for xiaohongshu main API requests.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        uri: API endpoint path (e.g., "/api/sns/web/v1/feed")
        cookies: Dictionary of cookies, must include 'a1' for signing
        params: Optional query parameters for GET requests
        payload: Optional JSON payload for POST requests
    
    Returns:
        Dictionary containing signed headers:
        - X-S: Signature
        - X-T: Timestamp
        - X-S-Common: Common signature
    
    Raises:
        ImportError: If xhshow library is not installed
        ValueError: If 'a1' cookie is missing (required for signing)
    
    Example:
        >>> cookies = {"a1": "your_a1_cookie_value", "web_session": "..."}
        >>> headers = sign_main_api("POST", "/api/sns/web/v1/feed", cookies, 
        ...                         payload={"source_note_id": "..."})
        >>> print(headers)
        {'X-S': '...', 'X-T': '...', 'X-S-Common': '...'}
    """
    _init_signing()
    
    if not cookies.get("a1"):
        raise ValueError("'a1' cookie is required for API signing")
    
    if method.upper() == "GET":
        return _xhshow.sign_headers_get(  # type: ignore
            uri, cookies, params=params, session=_session
        )
    else:  # POST, PUT, etc.
        return _xhshow.sign_headers_post(  # type: ignore
            uri, cookies, payload=payload, session=_session
        )


def build_get_url(uri: str, params: dict[str, Any]) -> str:
    """
    Build a signed GET URL with query parameters.
    
    Args:
        uri: API endpoint path
        params: Query parameters
    
    Returns:
        Full URL with signed query string
    """
    _init_signing()
    return _xhshow.build_url(uri, params)  # type: ignore


def get_common_headers() -> dict[str, str]:
    """
    Get common headers that should be included in all API requests.
    
    Returns:
        Dictionary of common headers (User-Agent, Referer, etc.)
    """
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": HOME_URL,
        "Referer": f"{HOME_URL}/",
    }
