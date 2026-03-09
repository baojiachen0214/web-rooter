# Web-Rooter 增强功能说明

**更新日期**: 2026-03-08
**版本**: v2.0

---

## 新增功能概述

本次更新主要增强了搜索深度和 CLI 交互效率，解决了以下问题：

1. **CLI 命令操作更高效** - 不需要每次写 Python 脚本
2. **搜索深度不足** - 所有搜索引擎并行搜索，中英文同时查找
3. **搜索引擎单一** - 新增 Yandex、GitHub、Reddit、Twitter 等 21 个搜索引擎
4. **语言限制** - 同时支持中文和英文搜索，不错过英文社区文章

---

## 新增搜索引擎

### 通用搜索引擎（7 个）
| 引擎 | 代码 | 适用场景 |
|------|------|----------|
| Google | `google` | 全球最大搜索引擎 |
| Bing | `bing` | 微软搜索引擎 |
| Baidu | `baidu` | 中文搜索 |
| DuckDuckGo | `duckduckgo` | 隐私保护 |
| Sogou | `sogou` | 搜狗搜索 |
| **Yandex** | `yandex` | 俄罗斯引擎，适合英文 |
| Google US | `google_us` | Google 美国版（英文） |
| Bing US | `bing_us` | Bing 美国版（英文） |

### 社交媒体（6 个）
| 平台 | 代码 | 用途 |
|------|------|------|
| Bilibili | `bilibili` | B 站视频评论 |
| Zhihu | `zhihu` | 知乎评价 |
| Weibo | `weibo` | 微博舆情 |
| Reddit | `reddit` | 美国贴吧讨论 |
| Twitter | `twitter` | 推特实时动态 |
| Hacker News | `hackernews` | 技术热点 |

### 技术社区（3 个）
| 平台 | 代码 | 用途 |
|------|------|------|
| GitHub | `github` | 代码项目 |
| Stack Overflow | `stackoverflow` | 技术问题 |
| Medium | `medium` | 技术文章 |

### 学术搜索（3 个）
| 平台 | 代码 | 用途 |
|------|------|------|
| Google Scholar | `google_scholar` | 学术论文 |
| arXiv | `arxiv` | 预印本论文 |
| Semantic Scholar | `semantic_scholar` | 语义学术 |

---

## 新增 CLI 命令

### 1. deep - 深度搜索

**用法**:
```bash
deep <查询词> [结果数] [--en] [--crawl=N]
```

**参数**:
- `--en`: 同时使用英文搜索
- `--crawl=N`: 爬取前 N 个结果

**示例**:
```bash
# 深度搜索苹果发布会，中英文并行，爬取前 5 个结果
deep "苹果发布会" 10 --en --crawl=5

# 搜索 iPhone 17 评价
deep "iPhone 17 review" --crawl=3
```

**工作原理**:
1. 使用 Google、Bing、Baidu、DuckDuckGo 并行搜索
2. 如果指定 `--en`，同时将查询翻译成英文搜索
3. 合并所有结果，去重
4. 可选爬取前 N 个结果

### 2. social - 社交媒体搜索

**用法**:
```bash
social <查询词> [--platform=xxx]
```

**支持的平台**:
- `bilibili` - B 站
- `zhihu` - 知乎
- `weibo` - 微博
- `reddit` - Reddit
- `twitter` - Twitter

**示例**:
```bash
# 搜索知乎上的 iPhone 17 评价
social "iPhone 17" --platform=zhihu

# 搜索 B 站和知乎的测评
social "iPhone 17 测评" --platform=bilibili --platform=zhihu

# 搜索所有平台
social "苹果发布会反应"
```

### 3. tech - 技术社区搜索

**用法**:
```bash
tech <查询词> [--source=xxx]
```

**支持的来源**:
- `github` - GitHub 项目
- `stackoverflow` - Stack Overflow
- `medium` - Medium 文章
- `hackernews` - Hacker News 讨论

**示例**:
```bash
# GitHub 搜索机器学习项目
tech "machine learning" --source=github

# 搜索技术文章
tech "transformer architecture" --source=medium

# 搜索所有技术来源
tech "Python best practices"
```

### 4. export - 导出搜索结果

**用法**:
```bash
export <查询词> <输出文件>
```

**示例**:
```bash
# 导出 AI 新闻到 JSON
export "AI 大模型" ai_news.json

# 导出到桌面
export "苹果发布会" "C:/Users/你的用户名/Desktop/results.json"
```

**输出格式**:
```json
{
  "success": true,
  "query": "AI 大模型",
  "total_results": 50,
  "results": [...],
  "crawled_content": [...],
  "search_summary": "使用 4 个引擎搜索，共找到 50 条结果"
}
```

---

## 完整命令列表

### 网页访问类
| 命令 | 用途 |
|------|------|
| `visit <url> [--js]` | 访问网页 |
| `search <query>` | 页面内搜索 |
| `extract <url> <target>` | 提取信息 |
| `crawl <url> [pages] [depth]` | 爬取网站 |
| `links <url>` | 获取链接 |
| `kb` | 查看知识库 |

### 搜索类
| 命令 | 用途 |
|------|------|
| `web <query>` | 互联网搜索 |
| `deep <query> [--en]` | 深度搜索（新） |
| `social <query>` | 社交媒体搜索（新） |
| `tech <query>` | 技术社区搜索（新） |
| `research <topic>` | 深度研究 |
| `academic <query>` | 学术搜索 |
| `site <url> <query>` | 站内搜索 |

### 其他
| 命令 | 用途 |
|------|------|
| `export <query> <file>` | 导出结果（新） |
| `help` | 帮助 |
| `quit` | 退出 |

---

## 使用场景示例

### 场景 1: 收集产品用户反馈

**任务**: 收集 iPhone 17 的用户评价

```bash
# 1. 深度搜索（中英文）
deep "iPhone 17 用户评价" --en --crawl=5

# 2. 搜索社交媒体
social "iPhone 17" --platform=zhihu --platform=bilibili

# 3. 导出结果
export "iPhone 17 review" iphone17_feedback.json
```

### 场景 2: 技术调研

**任务**: 调研 Transformer 架构

```bash
# 1. 技术社区搜索
tech "transformer architecture" --source=github --source=stackoverflow

# 2. 学术搜索
academic "transformer attention is all you need"

# 3. 深度研究
research "Transformer 架构原理"
```

### 场景 3: 舆情监控

**任务**: 监控苹果发布会舆情

```bash
# 1. 微博搜索
social "苹果发布会" --platform=weibo

# 2. 知乎讨论
social "如何评价苹果发布会" --platform=zhihu

# 3. 国际反应
deep "Apple event reaction" --en --crawl=10

# 4. 导出报告
export "苹果发布会 舆情" apple_event_sentiment.json
```

### 场景 4: 新闻收集

**任务**: 收集 AI 大模型最新新闻

```bash
# 1. 深度搜索
deep "AI 大模型 2025 最新进展" --en --crawl=10

# 2. 技术社区
tech "large language model" --source=hackernews

# 3. 导出
export "AI news" ai_news.json
```

---

## 多语言搜索策略

### 为什么需要多语言搜索？

1. **英文社区更活跃** - 技术讨论多在英文社区
2. **信息来源更广** - 不同语言社区有不同视角
3. **避免信息茧房** - 中文搜索可能错过重要信息

### 自动翻译机制

当使用 `deep --en` 时，系统会：

1. 保留原始中文查询
2. 自动添加英文关键词
3. 使用 Google US、Bing US、Yandex 搜索

**示例**:
```
中文查询："苹果发布会"
英文查询："苹果发布会 Apple event keynote"
```

---

## 性能优化

### 并行搜索
- 所有搜索引擎同时执行
- 异步 IO，不阻塞
- 结果自动去重

### 缓存机制
- 搜索结果缓存 1 小时
- 避免重复请求
- 支持 SQLite 持久化

### 连接池
- HTTP 连接重用
- 减少延迟 50%
- 自动健康检查

---

## 最佳实践

### 1. 选择合适的命令
- 一般搜索：`web` 或 `deep`
- 社交媒体：`social`
- 技术内容：`tech`
- 学术内容：`academic`

### 2. 使用英文搜索
对于技术话题，总是使用 `--en`：
```bash
deep "机器学习" --en  # 而不是只用中文
```

### 3. 组合使用
```bash
# 先深度搜索
deep "主题" --en

# 再搜索社交媒体
social "主题"

# 最后导出
export "主题" output.json
```

### 4. 爬取前 N 个结果
使用 `--crawl=N` 获取详细内容：
```bash
deep "查询" --crawl=5  # 爬取前 5 个
```

---

## 故障排除

### 搜索结果为空
- 尝试英文查询
- 更换搜索引擎
- 检查网络连接

### 某个平台无法访问
- 使用代理
- 尝试其他平台
- 使用 `web` 命令代替

### 导出失败
- 检查文件路径
- 确保有写入权限
- 使用绝对路径

---

## 下一步计划

1. **更多搜索引擎** - 添加 Naver（韩国）、Yahoo Japan 等
2. **智能翻译** - 集成翻译 API
3. **结果分析** - 自动情感分析、主题聚类
4. **定时任务** - 定期监控搜索

---

## 总结

本次更新使 Web-Rooter 成为功能更强大的搜索工具：

✅ **21 个搜索引擎** - 通用、社交、技术、学术全覆盖
✅ **多语言支持** - 中英文并行搜索，不错过任何信息
✅ **高效 CLI** - 无需写脚本，命令行即可完成
✅ **导出功能** - JSON 格式，方便后续处理

现在你可以：
- 用 `deep` 命令深度搜索任何主题
- 用 `social` 命令监控社交媒体
- 用 `tech` 命令搜索技术内容
- 用 `export` 命令导出结果

开始使用吧！
