"""Constants for XHS API client."""

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

# Config directory (within Web-Rooter's config)
CONFIG_DIR_NAME = ".web-rooter"
COOKIE_FILE = "xhs_cookies.json"
TOKEN_CACHE_FILE = "xhs_token_cache.json"
INDEX_CACHE_FILE = "xhs_index_cache.json"
