"""
Xiaohongshu API error codes and their meanings.

These error codes are reverse-engineered from the XHS web API responses.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Optional


class XhsErrorCode(IntEnum):
    """Common XHS API error codes."""
    
    # Success
    SUCCESS = 0
    
    # Authentication / Session errors
    SESSION_EXPIRED = -100  # Session expired, need re-login
    NEED_LOGIN = -1  # Need to login
    TOKEN_INVALID = 10001  # Invalid token
    TOKEN_EXPIRED = 10002  # Token expired
    
    # Rate limiting / Anti-spam
    RATE_LIMITED = 461  # Too many requests
    NEED_VERIFY = 471  # Need CAPTCHA verification
    IP_BLOCKED = 462  # IP address blocked
    
    # Content errors
    CONTENT_NOT_FOUND = 404  # Note/user not found
    CONTENT_DELETED = 410  # Content deleted
    CONTENT_BLOCKED = 451  # Content blocked/unavailable
    
    # Permission errors
    PERMISSION_DENIED = 403  # No permission to access
    PRIVATE_ACCOUNT = 430  # Private account
    
    # Request errors
    BAD_REQUEST = 400  # Invalid request parameters
    MISSING_PARAM = 10003  # Missing required parameter
    INVALID_PARAM = 10004  # Invalid parameter value
    
    # Server errors
    SERVER_ERROR = 500  # Internal server error
    SERVICE_UNAVAILABLE = 503  # Service temporarily unavailable


# Error code to user-friendly message mapping
ERROR_MESSAGES: dict[int, str] = {
    XhsErrorCode.SUCCESS: "Success",
    XhsErrorCode.SESSION_EXPIRED: "Session expired — please login again with: wr xhs login",
    XhsErrorCode.NEED_LOGIN: "Authentication required — please login with: wr xhs login",
    XhsErrorCode.TOKEN_INVALID: "Invalid authentication token",
    XhsErrorCode.TOKEN_EXPIRED: "Authentication token expired",
    XhsErrorCode.RATE_LIMITED: "Too many requests — please slow down",
    XhsErrorCode.NEED_VERIFY: "CAPTCHA verification required — try browser login: wr xhs login --browser",
    XhsErrorCode.IP_BLOCKED: "IP address blocked — try using a different network",
    XhsErrorCode.CONTENT_NOT_FOUND: "Content not found",
    XhsErrorCode.CONTENT_DELETED: "Content has been deleted",
    XhsErrorCode.CONTENT_BLOCKED: "Content is blocked or unavailable",
    XhsErrorCode.PERMISSION_DENIED: "Permission denied — you don't have access to this content",
    XhsErrorCode.PRIVATE_ACCOUNT: "This account is private",
    XhsErrorCode.BAD_REQUEST: "Invalid request",
    XhsErrorCode.MISSING_PARAM: "Missing required parameter",
    XhsErrorCode.INVALID_PARAM: "Invalid parameter value",
    XhsErrorCode.SERVER_ERROR: "Server error — please try again later",
    XhsErrorCode.SERVICE_UNAVAILABLE: "Service temporarily unavailable",
}


def get_error_message(code: int, default: Optional[str] = None) -> str:
    """
    Get user-friendly error message for an error code.
    
    Args:
        code: Error code from API response
        default: Default message if code not found
        
    Returns:
        User-friendly error message
    """
    return ERROR_MESSAGES.get(code, default or f"Unknown error (code: {code})")


def is_auth_error(code: int) -> bool:
    """Check if error code is authentication-related."""
    return code in (
        XhsErrorCode.SESSION_EXPIRED,
        XhsErrorCode.NEED_LOGIN,
        XhsErrorCode.TOKEN_INVALID,
        XhsErrorCode.TOKEN_EXPIRED,
    )


def is_rate_limit_error(code: int) -> bool:
    """Check if error code is rate limiting related."""
    return code in (
        XhsErrorCode.RATE_LIMITED,
        XhsErrorCode.NEED_VERIFY,
        XhsErrorCode.IP_BLOCKED,
    )


def is_content_error(code: int) -> bool:
    """Check if error code is content-related (not found, deleted, etc)."""
    return code in (
        XhsErrorCode.CONTENT_NOT_FOUND,
        XhsErrorCode.CONTENT_DELETED,
        XhsErrorCode.CONTENT_BLOCKED,
        XhsErrorCode.PRIVATE_ACCOUNT,
    )
