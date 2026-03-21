"""
Shared TLS helpers for outbound HTTP clients.
"""

from __future__ import annotations

import logging
import os
import ssl

try:
    import certifi
except ModuleNotFoundError:  # pragma: no cover - optional dependency fallback
    certifi = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_CA_FILE_ENV_KEYS = (
    "WEB_ROOTER_SSL_CA_FILE",
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
)


def build_client_ssl_context() -> ssl.SSLContext:
    """
    Build a resilient SSL context for aiohttp clients.

    Preference order:
    1. Explicit CA file from environment.
    2. certifi bundle when available.
    3. Python/system default certificate store.
    """
    for env_name in _CA_FILE_ENV_KEYS:
        ca_file = str(os.getenv(env_name, "")).strip()
        if not ca_file:
            continue
        try:
            return ssl.create_default_context(cafile=ca_file)
        except Exception as exc:
            logger.warning("Ignoring invalid CA bundle from %s=%s: %s", env_name, ca_file, exc)

    if certifi is not None:
        try:
            return ssl.create_default_context(cafile=certifi.where())
        except Exception as exc:
            logger.warning("Falling back to system CA store after certifi error: %s", exc)

    return ssl.create_default_context()
