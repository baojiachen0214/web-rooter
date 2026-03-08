# Web-Rooter 改进计划 - 实施总结

本文档总结了为 web-rooter 项目实现的所有改进功能，灵感来自 Scrapling 项目。

## 已完成的改进

### 1. 配置系统增强 (`config.py`)

新增了以下配置类：

#### `ProxyRotationStrategy` (枚举)
- `ROUND_ROBIN`: 循环轮换策略
- `RANDOM`: 随机选择策略
- `SUCCESS_BASED`: 基于成功率的策略

#### `ProxyConfig` (数据类)
- `PROXIES`: 代理列表
- `ROTATION_STRATEGY`: 轮换策略
- `PROXY_TIMEOUT`: 代理超时
- `AUTO_DETECT_FAILURE`: 自动检测失败代理
- `FAILURE_THRESHOLD`: 失败阈值
- `MAX_REUSE`: 代理重用次数

#### `StealthConfig` (数据类)
- `ENABLE_STEALTH`: 启用隐身模式
- `RANDOM_USER_AGENT`: 随机 User-Agent
- `USER_AGENTS`: User-Agent 列表
- `CANVAS_NOISE`: Canvas 指纹噪声
- `DISABLE_WEBRTC`: WebRTC 控制
- `BLOCK_RESOURCES`: 资源拦截
- `AUTO_CLOUDFLARE`: Cloudflare 自动处理
- `RANDOM_VIEWPORT`: 随机屏幕分辨率
- `TIMEZONE`: 时区设置

#### `AdaptiveParserConfig` (数据类)
- `ENABLE_ADAPTIVE`: 启用自适应模式
- `SIMILARITY_THRESHOLD`: 相似度阈值
- 权重配置（标签、属性、文本、位置）
- `STORAGE_PATH`: 存储路径
- `CACHE_EXPIRY_DAYS`: 缓存过期时间

### 2. 自适应解析器 (`core/parser.py`)

#### 新增类

**`ElementFeature` (数据类)**
- 存储元素特征用于自适应匹配
- 包含：标签名、属性、文本、类名、位置等

**`AdaptiveParser` (Parser 子类)**
- `select_adaptive(selector, auto_save)`: 自适应 CSS 选择器
- `find_adaptive(...)`: 自适应查找元素
- `save_feature(selector, element)`: 保存元素特征
- `_find_similar_element(feature)`: 查找相似元素
- `_compute_similarity(f1, f2)`: 计算相似度
- 支持四种相似度计算：标签、属性、文本、位置

**`AttributesHandler`**
- `get(name, default)`: 获取属性
- `has(name)`: 检查属性
- `all()`: 获取所有属性
- `get_href(absolute, base_url)`: 获取 href
- `get_src(absolute, base_url)`: 获取 src
- `get_class()`: 获取 class
- `get_data_attrs()`: 获取 data-* 属性
- `get_aria_attrs()`: 获取 aria-* 属性

**`TextHandler`**
- `get(strip, separator)`: 获取文本
- `get_all(strip)`: 获取所有文本节点
- `find(pattern, regex)`: 查找匹配文本
- `normalize(whitespace)`: 归一化文本
- `get_int(default)`: 提取整数
- `get_float(default)`: 提取浮点数
- `get_number(default)`: 提取数字（支持百分比、货币）

**`CSSToXPath`**
- `convert(css_selector)`: CSS 转 XPath
- `convert_back(xpath)`: XPath 转 CSS（近似）

#### 增强方法

**`Parser` 类新增:**
- `select_one(selector)`: 获取第一个匹配元素
- `generate_css_selector(element)`: 为元素生成 CSS 选择器
- `generate_xpath(element)`: 为元素生成 XPath

### 3. 隐身浏览器增强 (`core/browser.py`)

#### 新增类

**`UserAgentGenerator`**
- `generate()`: 生成随机 User-Agent
- `get_platform_info()`: 获取平台信息

**`FingerprintGenerator`**
- `generate_canvas_noise()`: 生成 canvas 噪声
- `get_screen_dims()`: 获取屏幕尺寸
- `get_timezone()`: 获取时区
- `get_languages()`: 获取语言列表

**`StealthInjector`**
- `get_init_scripts(config)`: 获取隐身脚本列表
- 包含 chrome_app、chrome_runtime、navigator_fix、canvas_noise、webgl_vendor、permissions 等脚本

#### 增强 `BrowserManager`

**新参数:**
- `stealth_config`: 隐身配置

**新方法:**
- `_stealth_route_handler(route)`: 隐身资源拦截
- `_inject_stealth_scripts()`: 注入隐身脚本
- `_handle_cloudflare(page, timeout)`: 处理 Cloudflare 验证

**增强的 `fetch` 方法:**
- 新增 `handle_cloudflare` 参数
- 支持自动处理 Cloudflare Turnstile 验证

### 4. 代理轮换 (`core/crawler.py`)

#### 新增类

**`ProxyRotator`**
- `get_proxy()`: 获取代理（异步）
- `record_success(proxy)`: 记录成功
- `record_failure(proxy)`: 记录失败
- `get_stats()`: 获取统计
- `reset_failures()`: 重置失败记录
- `add_proxy(proxy_str)`: 添加代理

**轮换策略:**
- `_get_round_robin()`: 循环轮换
- `_get_random()`: 随机选择
- `_get_success_based()`: 基于成功率

#### 增强 `Crawler`

**新参数:**
- `proxy_config`: 代理配置
- `use_proxy_rotation`: 启用代理轮换

**增强的 `fetch` 方法:**
- 新增 `use_proxy` 参数
- 自动代理轮换
- 代理错误检测和处理

**增强的 `fetch_with_retry` 方法:**
- 重试时自动轮换代理
- 最后一次重试重置失败记录

### 5. 元素特征存储 (`core/element_storage.py`)

#### 新增模块

**`ElementFeature` (数据类)**
- 完整的元素特征数据结构
- `to_dict()`: 转为字典
- `from_row(row)`: 从数据库行创建

**`ElementStorageSystem`**
- `save_feature(feature)`: 保存特征
- `get_features(url, selector)`: 获取特征
- `update_access(feature, success)`: 更新访问统计
- `cleanup_expired(days)`: 清理过期缓存
- `cleanup_low_success(min_success_rate)`: 清理低成功率缓存
- `get_stats()`: 获取统计信息

**辅助函数:**
- `compute_text_hash(text)`: 计算文本哈希
- `get_parent_path(element, max_depth)`: 获取父元素路径
- `get_sibling_index(element)`: 获取兄弟索引
- `generate_xpath(element)`: 生成 XPath

## 使用示例

### 1. 自适应解析器

```python
from core.parser import AdaptiveParser

# 创建自适应解析器
parser = AdaptiveParser(
    adaptive=True,
    similarity_threshold=0.6,
)

# 解析页面
parser.parse(html, url)

# 使用自适应选择器（选择器失效时自动查找相似元素）
elements = parser.select_adaptive("div.article-title")

# 手动保存特征
element = parser.select_one("div.title")
if element:
    parser.save_feature("div.title", element)
```

### 2. 隐身浏览器

```python
from core.browser import BrowserManager
from config import StealthConfig

# 创建隐身配置
stealth_config = StealthConfig(
    ENABLE_STEALTH=True,
    RANDOM_USER_AGENT=True,
    CANVAS_NOISE=True,
    DISABLE_WEBRTC=True,
    AUTO_CLOUDFLARE=True,
)

# 创建浏览器管理器
browser = BrowserManager(stealth_config=stealth_config)

async with browser:
    # 获取页面（自动处理 Cloudflare）
    result = await browser.fetch(
        url="https://example.com",
        handle_cloudflare=True,
    )
    print(result.html)
```

### 3. 代理轮换

```python
from core.crawler import Crawler, ProxyRotator
from config import ProxyConfig, ProxyRotationStrategy

# 创建代理配置
proxy_config = ProxyConfig(
    PROXIES=[
        "http://proxy1.example.com:8080",
        "http://proxy2.example.com:8080",
        "http://proxy3.example.com:8080",
    ],
    ROTATION_STRATEGY=ProxyRotationStrategy.ROUND_ROBIN,
    MAX_REUSE=5,
)

# 创建带代理轮换的爬虫
crawler = Crawler(
    proxy_config=proxy_config,
    use_proxy_rotation=True,
)

# 获取页面（自动使用代理）
result = await crawler.fetch_with_retry("https://example.com")
```

### 4. 属性处理器

```python
from core.parser import AttributesHandler
from bs4 import BeautifulSoup

soup = BeautifulSoup(html, "lxml")
element = soup.select_one("a.link")

handler = AttributesHandler(element)

# 获取属性
href = handler.get_href(absolute=True, base_url="https://example.com")
classes = handler.get_class()
data_attrs = handler.get_data_attrs()
aria_attrs = handler.get_aria_attrs()
```

### 5. 文本处理器

```python
from core.parser import TextHandler
from bs4 import BeautifulSoup

soup = BeautifulSoup(html, "lxml")
element = soup.select_one("div.price")

handler = TextHandler(element)

# 获取文本
text = handler.get()
normalized = handler.normalize()

# 提取数字
price = handler.get_float()
discount = handler.get_number()  # 支持百分比

# 查找文本
matches = handler.find("价格")
```

### 6. CSS 转 XPath

```python
from core.parser import CSSToXPath

css = "div.container > h1.title"
xpath = CSSToXPath.convert(css)
# 输出：//div[contains(concat(' ', normalize-space(@class), ' '), ' container ')]/h1[contains(concat(' ', normalize-space(@class), ' '), ' title ')]
```

## 测试

运行测试文件验证所有功能：

```bash
python test_improvements.py
```

## 配置说明

### 环境变量（可选）

可以通过 `.env` 文件配置：

```env
# 代理配置
PROXY_LIST=http://proxy1:8080,http://proxy2:8080
PROXY_STRATEGY=round_robin

# 隐身配置
ENABLE_STEALTH=true
RANDOM_USER_AGENT=true
```

## 性能优化建议

1. **自适应解析器**: 对于频繁爬取的网站，启用 adaptive 模式可以减少网站更新导致的爬取失败
2. **隐身模式**: 对于有反爬虫的网站，启用隐身模式并配置 Cloudflare 自动处理
3. **代理轮换**: 大规模爬取时配置多个代理并使用轮换策略
4. **资源拦截**: 配置 BLOCK_IMAGES 和 BLOCK_FONTS 加快加载速度

## 注意事项

1. 自适应解析器需要先成功获取一次元素才能保存特征
2. 隐身模式需要安装 Playwright (`playwright install chromium`)
3. 代理轮换需要有效的代理服务器列表
4. Cloudflare 自动处理主要针对 Turnstile 验证，复杂验证可能需要额外处理

## 后续改进建议

1. 集成 SQLite 存储元素特征（已有 `element_storage.py` 但未完全集成到 AdaptiveParser）
2. 添加更多隐身脚本（如更完善的 WebGL 指纹模拟）
3. 支持更多代理协议（SOCKS5 等）
4. 添加代理健康检查功能
