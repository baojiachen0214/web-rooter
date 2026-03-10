"""
示例后处理器。

加载方式：
  python main.py processors --load=plugins/post_processors/example_processor.py:create_processor --force
"""
from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urlparse


class DomainBucketProcessor:
    name = "domain_bucket"

    def process(self, result: Dict[str, Any], context: Any) -> Dict[str, Any]:
        payload = dict(result or {})
        results = payload.get("results", [])
        if not isinstance(results, list):
            results = []

        bucket: Dict[str, int] = {}
        for item in results:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "")
            host = (urlparse(url).hostname or "").lower()
            if not host:
                continue
            bucket[host] = bucket.get(host, 0) + 1

        payload.setdefault("analysis", {})
        payload["analysis"]["domain_bucket"] = dict(
            sorted(bucket.items(), key=lambda kv: kv[1], reverse=True)
        )
        payload["analysis"]["postprocess_query"] = getattr(context, "query", "")
        return payload


def create_processor() -> DomainBucketProcessor:
    return DomainBucketProcessor()

