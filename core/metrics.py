"""
指标导出 - 爬取统计和监控

功能:
- 实时爬取统计
- 代理池统计
- Prometheus 指标格式导出
- JSON 导出

用法:
    metrics = MetricsCollector()
    metrics.record_request(url, status, elapsed)

    # 导出为 Prometheus 格式
    print(metrics.to_prometheus())

    # 导出为 JSON
    print(metrics.to_json())
"""
import time
import json
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from collections import defaultdict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class RequestMetric:
    """单次请求指标"""
    url: str
    status_code: int
    elapsed: float  # 毫秒
    timestamp: float = field(default_factory=time.time)
    error: Optional[str] = None
    proxy: Optional[str] = None
    from_cache: bool = False


@dataclass
class CrawlerMetrics:
    """爬虫聚合指标"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    cached_requests: int = 0

    total_bytes: int = 0
    total_elapsed: float = 0

    status_codes: Dict[int, int] = field(default_factory=lambda: defaultdict(int))
    errors: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    start_time: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)

    def add_request(self, metric: RequestMetric):
        """添加请求指标"""
        self.total_requests += 1
        self.last_updated = time.time()

        if metric.from_cache:
            self.cached_requests += 1

        if 200 <= metric.status_code < 400:
            self.successful_requests += 1
        else:
            self.failed_requests += 1

        self.status_codes[metric.status_code] += 1

        if metric.error:
            self.errors[metric.error] += 1

        self.total_elapsed += metric.elapsed


class MetricsCollector:
    """
    指标收集器

    功能:
    - 收集请求指标
    - 聚合统计
    - 导出为 Prometheus/JSON 格式

    用法:
        collector = MetricsCollector()
        collector.record_request(...)
        print(collector.get_summary())
    """

    def __init__(self, max_history: int = 10000):
        """
        初始化指标收集器

        Args:
            max_history: 最大历史记录数
        """
        self._history: List[RequestMetric] = []
        self._max_history = max_history
        self._aggregated = CrawlerMetrics()

        # 按域名统计
        self._by_domain: Dict[str, CrawlerMetrics] = defaultdict(CrawlerMetrics)

        # 代理统计
        self._proxy_stats: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"success": 0, "failure": 0}
        )

        # 每秒请求数历史 (用于计算 QPS)
        self._requests_per_second: List[float] = []
        self._last_qps_calculation = time.time()

    def record_request(
        self,
        url: str,
        status_code: int,
        elapsed: float,
        error: Optional[str] = None,
        proxy: Optional[str] = None,
        from_cache: bool = False,
        bytes_transferred: int = 0,
    ):
        """
        记录请求指标

        Args:
            url: 请求 URL
            status_code: 状态码
            elapsed: 耗时 (毫秒)
            error: 错误信息
            proxy: 使用的代理
            from_cache: 是否来自缓存
            bytes_transferred: 传输字节数
        """
        metric = RequestMetric(
            url=url,
            status_code=status_code,
            elapsed=elapsed,
            error=error,
            proxy=proxy,
            from_cache=from_cache,
        )

        # 添加到历史记录
        self._history.append(metric)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        # 聚合
        self._aggregated.add_request(metric)
        self._aggregated.total_bytes += bytes_transferred

        # 按域名统计
        domain = self._extract_domain(url)
        self._by_domain[domain].add_request(metric)
        self._by_domain[domain].total_bytes += bytes_transferred

        # 代理统计
        if proxy:
            if 200 <= status_code < 400:
                self._proxy_stats[proxy]["success"] += 1
            else:
                self._proxy_stats[proxy]["failure"] += 1

        # 更新 QPS
        self._update_qps()

    def _extract_domain(self, url: str) -> str:
        """从 URL 提取域名"""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc or "unknown"

    def _update_qps(self):
        """更新 QPS 统计"""
        now = time.time()

        # 每秒计算一次 QPS
        if now - self._last_qps_calculation >= 1.0:
            elapsed = now - self._aggregated.start_time
            if elapsed > 0:
                qps = self._aggregated.total_requests / elapsed
                self._requests_per_second.append(qps)

                # 只保留最近 60 秒
                if len(self._requests_per_second) > 60:
                    self._requests_per_second.pop(0)

            self._last_qps_calculation = now

    def get_summary(self) -> Dict[str, Any]:
        """
        获取摘要统计

        Returns:
            统计信息字典
        """
        elapsed = time.time() - self._aggregated.start_time

        summary = {
            "total_requests": self._aggregated.total_requests,
            "successful_requests": self._aggregated.successful_requests,
            "failed_requests": self._aggregated.failed_requests,
            "cached_requests": self._aggregated.cached_requests,
            "total_bytes": self._aggregated.total_bytes,
            "total_elapsed_ms": self._aggregated.total_elapsed,
            "success_rate": self._aggregated.successful_requests / max(1, self._aggregated.total_requests),
            "cache_hit_rate": self._aggregated.cached_requests / max(1, self._aggregated.total_requests),
            "avg_response_time_ms": self._aggregated.total_elapsed / max(1, self._aggregated.total_requests),
            "requests_per_second": self._aggregated.total_requests / max(1, elapsed),
            "elapsed_seconds": elapsed,
            "status_codes": dict(self._aggregated.status_codes),
            "errors": dict(self._aggregated.errors),
        }

        # QPS 统计
        if self._requests_per_second:
            summary["current_qps"] = self._requests_per_second[-1]
            summary["avg_qps"] = sum(self._requests_per_second) / len(self._requests_per_second)
            summary["max_qps"] = max(self._requests_per_second)

        # 域名统计
        summary["by_domain"] = {
            domain: {
                "requests": metrics.total_requests,
                "success_rate": metrics.successful_requests / max(1, metrics.total_requests),
            }
            for domain, metrics in list(self._by_domain.items())[:10]  # 前 10 个域名
        }

        # 代理统计
        summary["proxy_stats"] = {
            proxy: {
                "success": stats["success"],
                "failure": stats["failure"],
                "success_rate": stats["success"] / max(1, stats["success"] + stats["failure"]),
            }
            for proxy, stats in self._proxy_stats.items()
        }

        return summary

    def to_prometheus(self) -> str:
        """
        导出为 Prometheus 指标格式

        Returns:
            Prometheus 格式的指标字符串
        """
        summary = self.get_summary()
        lines = []

        # 计数器
        lines.append("# HELP web_rooter_requests_total Total requests")
        lines.append("# TYPE web_rooter_requests_total counter")
        lines.append(f"web_rooter_requests_total {summary['total_requests']}")

        lines.append("# HELP web_rooter_requests_success Successful requests")
        lines.append("# TYPE web_rooter_requests_success counter")
        lines.append(f"web_rooter_requests_success {summary['successful_requests']}")

        lines.append("# HELP web_rooter_requests_failed Failed requests")
        lines.append("# TYPE web_rooter_requests_failed counter")
        lines.append(f"web_rooter_requests_failed {summary['failed_requests']}")

        lines.append("# HELP web_rooter_requests_cached Cached requests")
        lines.append("# TYPE web_rooter_requests_cached counter")
        lines.append(f"web_rooter_requests_cached {summary['cached_requests']}")

        lines.append("# HELP web_rooter_bytes_total Total bytes transferred")
        lines.append("# TYPE web_rooter_bytes_total counter")
        lines.append(f"web_rooter_bytes_total {summary['total_bytes']}")

        # 状态码
        lines.append("# HELP web_rooter_status_code Requests by status code")
        lines.append("# TYPE web_rooter_status_code counter")
        for code, count in summary["status_codes"].items():
            lines.append(f'web_rooter_status_code{{code="{code}"}} {count}')

        # QPS
        if "current_qps" in summary:
            lines.append("# HELP web_rooter_qps_current Current requests per second")
            lines.append("# TYPE web_rooter_qps_current gauge")
            lines.append(f"web_rooter_qps_current {summary['current_qps']:.2f}")

        # 响应时间
        lines.append("# HELP web_rooter_response_time_avg Average response time (ms)")
        lines.append("# TYPE web_rooter_response_time_avg gauge")
        lines.append(f"web_rooter_response_time_avg {summary['avg_response_time_ms']:.2f}")

        return "\n".join(lines)

    def to_json(self) -> str:
        """
        导出为 JSON 格式

        Returns:
            JSON 字符串
        """
        return json.dumps(self.get_summary(), indent=2, default=str)

    def get_recent_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的错误"""
        errors = [
            {
                "url": m.url,
                "status_code": m.status_code,
                "error": m.error,
                "timestamp": datetime.fromtimestamp(m.timestamp).isoformat(),
            }
            for m in self._history
            if m.error or m.status_code >= 400
        ]
        return errors[-limit:]

    def get_slow_requests(self, threshold_ms: float = 1000, limit: int = 10) -> List[Dict[str, Any]]:
        """获取慢请求"""
        slow = [
            {
                "url": m.url,
                "elapsed_ms": m.elapsed,
                "status_code": m.status_code,
                "timestamp": datetime.fromtimestamp(m.timestamp).isoformat(),
            }
            for m in self._history
            if m.elapsed > threshold_ms
        ]
        return slow[-limit:]

    def reset(self):
        """重置所有指标"""
        self._history.clear()
        self._aggregated = CrawlerMetrics()
        self._by_domain.clear()
        self._proxy_stats.clear()
        self._requests_per_second.clear()
        logger.info("Metrics reset")


class ProxyPoolMetrics:
    """
    代理池指标

    用法:
        proxy_metrics = ProxyPoolMetrics()
        proxy_metrics.record_use(proxy, success=True)
        print(proxy_metrics.get_stats())
    """

    def __init__(self):
        self._proxy_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "success": 0,
                "failure": 0,
                "total_elapsed": 0.0,
                "last_used": None,
                "consecutive_failures": 0,
            }
        )

    def record_use(
        self,
        proxy: str,
        success: bool,
        elapsed: float = 0.0,
    ):
        """记录代理使用"""
        stats = self._proxy_stats[proxy]

        if success:
            stats["success"] += 1
            stats["consecutive_failures"] = 0
        else:
            stats["failure"] += 1
            stats["consecutive_failures"] += 1

        stats["total_elapsed"] += elapsed
        stats["last_used"] = datetime.now().isoformat()

    def get_stats(self) -> Dict[str, Any]:
        """获取代理池统计"""
        result = {}

        for proxy, stats in self._proxy_stats.items():
            total = stats["success"] + stats["failure"]
            result[proxy] = {
                "total_requests": total,
                "success": stats["success"],
                "failure": stats["failure"],
                "success_rate": stats["success"] / max(1, total),
                "avg_elapsed_ms": stats["total_elapsed"] / max(1, total),
                "consecutive_failures": stats["consecutive_failures"],
                "last_used": stats["last_used"],
            }

        return result

    def get_unhealthy_proxies(self, failure_threshold: int = 5) -> List[str]:
        """获取不健康的代理"""
        unhealthy = []

        for proxy, stats in self._proxy_stats.items():
            if stats["consecutive_failures"] >= failure_threshold:
                unhealthy.append(proxy)

        return unhealthy

    def reset(self):
        """重置统计"""
        self._proxy_stats.clear()


# 全局指标收集器
_global_collector: Optional[MetricsCollector] = None


def get_global_collector() -> MetricsCollector:
    """获取全局指标收集器"""
    global _global_collector
    if _global_collector is None:
        _global_collector = MetricsCollector()
    return _global_collector


def record_request(**kwargs):
    """便捷函数：记录请求指标"""
    get_global_collector().record_request(**kwargs)


def get_metrics_summary() -> Dict[str, Any]:
    """便捷函数：获取指标摘要"""
    return get_global_collector().get_summary()


def export_prometheus_metrics() -> str:
    """便捷函数：导出 Prometheus 指标"""
    return get_global_collector().to_prometheus()
