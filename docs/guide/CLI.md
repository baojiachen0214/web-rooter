# CLI Guide

## Philosophy

- `quick` 是默认入口：忘记命令细节时优先用它
- URL 访问优先 `visit`，跨站信息检索优先 `web/deep`
- 深度搜索与深度爬取分离，避免默认过重

## Core Commands

```bash
python main.py help
python main.py doctor
python main.py quick <url|query> [--js] [--crawl-pages=N]
python main.py visit <url> [--js]
python main.py web <query> [--no-crawl] [--crawl-pages=N]
python main.py deep <query> [--en] [--crawl=N] [--num-results=N] [--variants=N] [--news] [--platforms] [--commerce] [--channel=x,y]
python main.py social <query> [--platform=xiaohongshu|zhihu|tieba|douyin|bilibili|weibo]
python main.py shopping <query> [--platform=taobao|jd|pinduoduo|meituan]
python main.py crawl <url> [pages] [depth] [--pattern=REGEX] [--allow-external] [--no-subdomains]
python main.py academic <query> [--papers-only|--with-code] [--no-abstracts] [--num-results=N] [--source=xxx]
```

## Typical Workflows

### 1) 快速查资料

```bash
python main.py quick "OpenAI Agents SDK"
```

### 2) 多引擎搜索 + 页面摘要

```bash
python main.py web "RAG benchmark 2026" --crawl-pages=5
```

### 3) 深度搜索（多查询变体）

```bash
python main.py deep "量化交易 因子" --variants=4 --crawl=5
```

### 3.1) 渠道扩展（媒体/平台站点）

```bash
python main.py deep "OpenAI 最新动态" --news
python main.py deep "AI Agent 工程实践" --platforms
python main.py deep "羽绒服选购" --commerce
python main.py deep "AI 芯片供应链" --channel=news,platforms,commerce
```

### 4) 站点定向爬取

```bash
python main.py crawl "https://docs.python.org/3/" 20 2 --pattern="/3/library/" --no-subdomains
```

### 5) 学术模式（带出处）

```bash
python main.py academic "RAG benchmark" --papers-only --source=arxiv --source=semantic_scholar
python main.py academic "Agent eval framework" --with-code --num-results=15 --source=github
```

## Notes

- `deep --variants` 用于子查询分解，默认值为 `1`
- `deep --news/--platforms/--commerce` 会自动扩展为 `site:domain` 查询，覆盖媒体、社交与电商站点
- `crawl` 默认不跨站，`--allow-external` 才会跨域
- 无法稳定用 HTTP 抓取时，优先 `visit --js` 或 `quick --js`
- `web/deep/academic/research` 输出包含 `citations` 字段；`deep/research` 还包含 `comparison` 交叉来源统计
