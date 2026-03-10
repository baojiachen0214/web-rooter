# MCP Tools Reference

以下为 `web-rooter` 暴露给 MCP 客户端的核心工具（以当前实现为准）。

| Tool | Purpose |
|---|---|
| `web_fetch` | HTTP 网页访问 |
| `web_fetch_js` | 浏览器网页访问（JS 渲染） |
| `web_search` | 在已访问内容中检索 |
| `web_search_internet` | 多引擎互联网搜索 |
| `web_search_combined` | 搜索 + 抓取组合 |
| `web_research` | 主题深度研究 |
| `web_search_academic` | 学术搜索 |
| `web_search_site` | 站内搜索 |
| `web_deep_search` | 深度并行搜索（多引擎+多查询） |
| `web_mindsearch` | MindSearch 图研究 |
| `web_search_social` | 社交媒体搜索 |
| `web_search_commerce` | 电商/本地生活平台搜索 |
| `web_search_tech` | 技术社区搜索 |
| `web_context_snapshot` | 全局深度抓取上下文快照 |
| `web_postprocessors` | 抓取结果后处理扩展管理 |
| `web_planners` | MindSearch planner 扩展管理 |
| `web_challenge_profiles` | challenge workflow profile 列表 |
| `web_extract` | 目标信息提取 |
| `web_crawl` | 站点深度爬取 |
| `parse_html` | HTML 解析 |
| `get_links` | 链接提取 |

## Practical Usage Order

1. `web_search_internet` / `web_research`
2. `web_fetch`（失败时 `web_fetch_js`）
3. `web_extract` / `parse_html`
4. 需要站点级遍历时再用 `web_crawl`

## Output Notes

- `web_search_internet` / `web_deep_search` / `web_research` / `web_search_academic` / `web_mindsearch` 返回结构化 `citations` 与可直接引用的 `references_text`
- `web_deep_search` / `web_research` 额外返回 `comparison`（来源交叉覆盖统计）
- `web_mindsearch` 额外返回 `mindsearch_compat`（`node` / `adjacency_list` / `ref2url`）
- `web_search_academic.sources` 支持：
  - `arxiv`, `google_scholar`, `semantic_scholar`, `pubmed`, `ieee`, `cnki`, `wanfang`, `paper_with_code`, `github`, `gitee`
