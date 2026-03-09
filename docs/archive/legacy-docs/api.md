# Web-Rooter API 文档

## 核心模块

### Spider - 爬虫基类

`agents/spider.py` 中的 `Spider` 类是所有爬虫的基类。

#### 基本用法

```python
from agents.spider import Spider

class MySpider(Spider):
    name = "myspider"
    start_urls = ["https://example.com"]

    async def parse(self, response):
        # 提取数据
        title = response.get_title()
        yield {"title": title, "url": response.url}

        # 跟随链接
        for link in response.get_links():
            yield response.follow(link["href"], callback="parse")

# 运行爬虫
spider = MySpider()
stats = await spider.run()
```

#### 配置选项

```python
from agents.spider import SpiderConfig

config = SpiderConfig(
    name="myspider",
    start_urls=["https://example.com"],
    concurrent_requests=16,      # 并发请求数
    download_delay=0.5,          # 下载延迟 (秒)
    randomize_delay=True,        # 随机延迟
    delay_range=(0.5, 2.0),      # 延迟范围
    max_requests_per_domain=100, # 每域名最大请求数
    max_retries=3,               # 最大重试次数
    persist=True,                # 启用持久化
    checkpoint_dir="./checkpoints",
)

spider = MySpider(config=config)
```

#### 流式输出 API

```python
# 流式获取结果
async with spider.stream(max_queue_size=100) as stream:
    stream_task = asyncio.create_task(stream.run())

    async for item in stream:
        if item.is_item:
            print(f"数据：{item.data}")
        elif item.is_error:
            print(f"错误：{item.data}")
        elif item.is_complete:
            print(f"完成：{item.data}")

    await stream_task
```

---

### Parser - 解析器

`core/parser.py` 提供 HTML 解析功能。

#### 基本用法

```python
from core.parser import Parser

parser = Parser()
parser.parse(html_content, url="https://example.com")

# 提取所有数据
data = parser.extract()
print(data.title)
print(data.text)
print(data.links)
```

#### 选择器增强

```python
# 完整 CSS 选择器生成
css = parser.generate_full_css_selector(element)
# 输出：html > body > div.container > main > article

# 完整 XPath 生成
xpath = parser.generate_full_xpath_selector(element, absolute=True)
# 输出：/html/body/div[@class='container']/main/article[1]

# 按文本查找
element = parser.find_by_text("登录")
elements = parser.find_all_by_text("文章")

# 正则表达式查找
element = parser.find_by_regex(r"\d{4}-\d{2}-\d{2}")
elements = parser.find_all_by_regex(r"price.*", name="span")
```

#### 自适应解析器

```python
from core.parser import AdaptiveParser

parser = AdaptiveParser(
    adaptive=True,
    similarity_threshold=0.6,
    use_db=True,
    db_path="./elements.db",
)

parser.parse(html, url)

# 当选择器失效时自动找到相似元素
elements = parser.select_adaptive("article.post")
```

---

### Crawler - 爬虫

`core/crawler.py` 提供 HTTP 请求功能。

#### 基本用法

```python
from core.crawler import Crawler

crawler = Crawler()
await crawler.open()

result = await crawler.fetch("https://example.com")
print(result.status_code)
print(result.html)

await crawler.close()
```

#### 缓存支持

```python
crawler = Crawler(
    use_cache=True,
    cache_ttl=3600,        # 缓存 TTL 1 小时
    cache_db_path="./cache.db",
)

# 首次请求
result1 = await crawler.fetch("https://example.com")
# 从缓存获取
result2 = await crawler.fetch("https://example.com")
```

#### 连接池

```python
crawler = Crawler(use_connection_pool=True)

# 连接会自动重用
result = await crawler.fetch("https://example.com")
```

#### 性能统计

```python
stats = crawler.get_performance_stats()
print(stats)
# {
#   "cache_hit_rate": 0.8,
#   "pool_hit_rate": 0.9,
#   "cache": {...},
#   "connection_pool": {...}
# }
```

---

### Result Queue - 结果队列

`core/result_queue.py` 提供流式输出支持。

#### 基本用法

```python
from core.result_queue import ResultQueue, StreamItem

queue = ResultQueue(maxsize=100)

# 放入数据
await queue.put({"title": "test"}, item_type="item")

# 获取数据
item = await queue.get(timeout=1.0)
if item and item.is_item:
    print(item.data)
```

#### 异步迭代

```python
async for item in queue:
    print(item.data)
```

---

### Cache - 缓存系统

`core/cache.py` 提供请求缓存。

#### 内存缓存

```python
from core.cache import MemoryCache, CacheEntry

cache = MemoryCache(max_size=1000)

entry = CacheEntry(
    url="https://example.com",
    response_body=b"content",
    status_code=200,
    headers={},
    ttl=3600,
)

await cache.set("key", entry)
result = await cache.get("key")
```

#### 请求缓存

```python
from core.cache import RequestCache

cache = RequestCache(
    use_memory=True,
    use_sqlite=True,
    db_path="./cache.db",
    default_ttl=3600,
)

await cache.set(
    url="https://example.com",
    response_body=b"content",
    status_code=200,
    headers={},
)

result = await cache.get("https://example.com")
```

---

### Connection Pool - 连接池

`core/connection_pool.py` 提供 HTTP 连接池。

#### 基本用法

```python
from core.connection_pool import ConnectionPool, PooledSession

pool = ConnectionPool(max_size=50, min_size=5)
await pool.start()

# 获取连接
session = await pool.get_connection("https://example.com")
async with session.get(url) as response:
    html = await response.text()

# 归还连接
await pool.return_connection(session, url)

await pool.stop()
```

#### 上下文管理器

```python
async with PooledSession(pool, url) as session:
    async with session.get(url) as response:
        html = await response.text()
```

---

### Metrics - 指标导出

`core/metrics.py` 提供监控指标。

#### 基本用法

```python
from core.metrics import MetricsCollector

collector = MetricsCollector()

collector.record_request(
    url="https://example.com",
    status_code=200,
    elapsed=150.5,
    bytes_transferred=1024,
)

# 获取摘要
summary = collector.get_summary()
```

#### Prometheus 导出

```python
prometheus_metrics = collector.to_prometheus()
print(prometheus_metrics)
# web_rooter_requests_total 100
# web_rooter_requests_success 95
# ...
```

#### JSON 导出

```python
json_metrics = collector.to_json()
```

---

## 响应对象

### Response

```python
@dataclass
class Response:
    url: str
    status: int
    headers: Dict[str, str]
    body: bytes
    text: str
    request: Optional[Request]
    cookies: Dict[str, str]
    elapsed: int  # 毫秒

    # 方法
    def json() -> Any          # 解析 JSON
    def get_title() -> str     # 获取标题
    def get_links() -> List    # 获取链接
    def get_text() -> str      # 获取文本
    def css(selector) -> List  # CSS 选择器
    def follow(url) -> Request # 跟随链接
```

---

## 请求对象

### Request

```python
@dataclass
class Request:
    url: str
    callback: str = "parse"
    priority: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    method: str = "GET"
    body: Optional[bytes] = None
    max_retries: int = 3
    proxy: Optional[str] = None

    # 方法
    def replace(**kwargs) -> Request  # 创建副本
    def to_dict() -> Dict             # 序列化
```

#### RequestBuilder

```python
from core.request import RequestBuilder

request = (RequestBuilder("https://example.com")
    .with_method("POST")
    .with_header("User-Agent", "...")
    .with_body(b"data")
    .with_priority(10)
    .build())
```

---

## 统计信息

### SpiderStats

```python
@dataclass
class SpiderStats:
    start_time: datetime
    end_time: Optional[datetime]
    requests_scheduled: int
    requests_downloaded: int
    requests_succeeded: int
    requests_failed: int
    items_scraped: int
    bytes_downloaded: int
    errors: Dict[str, int]

    def to_dict() -> Dict[str, Any]
```

---

## 错误处理

所有模块都使用标准 Python 异常：

- `asyncio.TimeoutError`: 请求超时
- `aiohttp.ClientError`: HTTP 错误
- `ValueError`: 参数错误

建议在爬虫中捕获异常：

```python
try:
    result = await crawler.fetch(url)
except asyncio.TimeoutError:
    logger.error(f"Timeout: {url}")
except aiohttp.ClientError as e:
    logger.error(f"HTTP error: {e}")
```
