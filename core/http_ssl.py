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
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


def is_insecure_ssl_enabled() -> bool:
    """Whether HTTP clients should skip TLS certificate verification."""
    return str(os.getenv("WEB_ROOTER_INSECURE_SSL", "")).strip().lower() in _TRUTHY_ENV_VALUES


def build_client_ssl_context() -> ssl.SSLContext:
    """
    Build a resilient SSL context for aiohttp clients.

    Preference order:
    1. Explicit CA file from environment.
    2. Python/system default certificate store, plus certifi bundle when available.
    3. Python/system default certificate store.
    """
    if is_insecure_ssl_enabled():
        logger.warning(
            "TLS certificate verification is disabled via WEB_ROOTER_INSECURE_SSL. "
            "Use this only for temporary troubleshooting on trusted networks."
        )
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    for env_name in _CA_FILE_ENV_KEYS:
        ca_file = str(os.getenv(env_name, "")).strip()
        if not ca_file:
            continue
        try:
            return ssl.create_default_context(cafile=ca_file)
        except Exception as exc:
            logger.warning("Ignoring invalid CA bundle from %s=%s: %s", env_name, ca_file, exc)

    context = ssl.create_default_context()

    if certifi is not None:
        try:
            # Preserve any local/system trust roots and append certifi's bundle
            # for environments whose OpenSSL store is incomplete.
            context.load_verify_locations(cafile=certifi.where())
        except Exception as exc:
            logger.warning("Falling back to system CA store after certifi error: %s", exc)

    return context
