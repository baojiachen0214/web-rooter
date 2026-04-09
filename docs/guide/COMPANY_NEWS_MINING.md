# 公司新闻中心批量抓取 — 完整使用手册

> 适用场景：批量抓取309家低数量公司的官网新闻中心，分页保存到本地，并生成质量验收报告。

---

## 一、所有文件位置速览

| 文件路径 | 类型 | 说明 |
|---|---|---|
| `profiles/skills/company_news_mining.skill.json` | Skill 配置 | AI 自动路由规则；`wr skills --resolve` 匹配入口 |
| `core/company_news_crawler.py` | 核心模块 | 批量抓取器，集成 job/checkpoint/queue/内存保护 |
| `core/postprocess.py` | 后处理器 | 新增 `NewsCountChangeProcessor`，统计新闻增量 |
| `tests/test_company_news_crawler.py` | 测试文件 | 27个单元测试，覆盖全部核心功能 |

**抓取输出目录结构**（以 `output_dir=0407stage2_archive` 为例）：

```
0407stage2_archive/
├── 示例科技/                     ← 每家公司一个子目录（公司ID）
│   ├── page_0001.html           ← 第1页原始HTML
│   ├── page_0001.meta.json      ← 第1页元数据（URL/时间/新闻链接数/citation）
│   ├── page_0002.html
│   ├── page_0002.meta.json
│   ├── ...
│   └── crawl_summary.json       ← 该公司抓取汇总（pages_fetched/total_news_links）
├── 另一家公司/
│   └── ...
├── .checkpoints/                ← 断点续爬检查点（自动管理，无需手动）
│   └── checkpoint_company_news_mining_latest.pkl
└── verification_report.json     ← 质量验收报告（全部公司汇总）
```

---

## 二、快速开始（CLI — 直接复制使用）

### 2.1 验证 skill 路由是否正确匹配

```bash
wr skills --resolve "309家公司新闻中心抓取" --compact
```

> 预期输出包含 `company_news_mining`，说明路由配置正确。

---

### 2.2 生成执行计划（dry-run，不实际抓取）

```bash
wr do-plan "批量抓取309家低数量公司的新闻中心，分页保存到本地" --skill company_news_mining
```

---

### 2.3 提交异步长任务（取代手动7组分批）

```bash
wr do-submit "批量抓取309家低数量公司新闻中心分页" \
    --skill company_news_mining \
    --crawl-pages=20 \
    --timeout-sec=7200
```

---

### 2.4 监控实时进度

```bash
# 查看所有任务
wr jobs

# 只看运行中的任务
wr jobs --status=running

# 查看某个任务的详细状态
wr job-status <job_id>

# 查看某个任务的完整结果
wr job-result <job_id>
```

---

### 2.5 查看内存/压力状态（处理大批量时使用）

```bash
wr pressure
wr telemetry
```

---

### 2.6 清理历史任务目录（防止磁盘堆积）

```bash
wr jobs-clean --keep=80 --days=7
```

---

## 三、Python API 用法（直接复制使用）

### 3.1 最简单的批量抓取

```python
import asyncio
from pathlib import Path
from core.company_news_crawler import CompanyRecord, run_batch

# 定义公司列表（从Excel/CSV读入后填写）
companies = [
    CompanyRecord(name="示例科技",   url="https://example.com",  news_count_before=5),
    CompanyRecord(name="测试集团",   url="https://test-corp.com", news_count_before=3),
    # ... 最多309家
]

# 一键批量抓取 + 自动生成验收报告
result = asyncio.run(run_batch(
    companies=companies,
    output_dir=Path("0407stage2_archive"),
    max_pages=20,           # 每家公司最多抓20页
    batch_size=50,          # 每50家公司为一批（自动分批，不用手动分7组）
    request_delay=0.5,      # 请求间隔0.5秒（对官网友好）
))

print("抓取完成:", result["crawl_stats"])
print("质量验收:", result["verification"])
```

---

### 3.2 断点续爬（程序中断后重新执行同一段代码即可）

```python
import asyncio
from pathlib import Path
from core.company_news_crawler import CompanyRecord, run_batch

companies = [...]  # 同上，全量309家，不需要手动去掉已完成的

# 直接重新执行，自动跳过已完成的公司（检查点自动恢复）
result = asyncio.run(run_batch(
    companies=companies,
    output_dir=Path("0407stage2_archive"),  # 与上次相同目录
    max_pages=20,
    checkpoint_dir=Path("0407stage2_archive/.checkpoints"),  # 与上次相同检查点目录
))
```

---

### 3.3 只抓取单家公司（调试用）

```python
import asyncio
from pathlib import Path
from core.company_news_crawler import crawl_news_pages

pages = asyncio.run(crawl_news_pages(
    company_url="https://example.com/news",
    output_dir=Path("0407stage2_archive"),
    company_id="示例科技",
    max_pages=5,        # 调试时只抓5页
    request_delay=1.0,  # 调试时放慢速度
    allow_browser=True, # 允许浏览器fallback（403时自动切换）
))

for p in pages:
    print(f"第{p.page_number}页: success={p.success}, 新闻链接数={p.news_links}, via_browser={p.via_browser}")
```

---

### 3.4 读取验收报告

```python
import json
from pathlib import Path

report = json.loads(Path("0407stage2_archive/verification_report.json").read_text(encoding="utf-8"))

print(f"总计: {report['total']} 家公司")
print(f"有改善: {report['improved']} 家")
print(f"无变化: {report['unchanged']} 家")
print(f"缺失(未抓到): {report['missing']} 家")

# 打印有改善的公司清单
for entry in report["improved_companies"]:
    print(f"  {entry['company_name']}: {entry['news_count_before']} → {entry['news_links_after']} (+{entry['increase']})")
```

---

### 3.5 读取单家公司的 meta.json（查看某页详情）

```python
import json
from pathlib import Path

meta = json.loads(
    Path("0407stage2_archive/示例科技/page_0001.meta.json").read_text(encoding="utf-8")
)

print("抓取URL:", meta["url"])
print("抓取时间:", meta["fetched_at"])
print("新闻链接数:", meta["news_links"])
print("是否走浏览器:", meta["via_browser"])
print("Citation信息:", meta["citation"])
```

---

### 3.6 使用后处理器统计新闻增量（质量验收）

```python
from core.postprocess import NewsCountChangeProcessor, PostProcessContext

processor = NewsCountChangeProcessor()
ctx = PostProcessContext(query="公司新闻抓取", mode="crawl")

# 构造结果数据（从 crawl_summary.json 读入后填写）
result = {
    "results": [
        {"company_id": "示例科技", "news_count_before": 5,  "news_links_after": 23},
        {"company_id": "测试集团", "news_count_before": 3,  "news_links_after": 2},
        {"company_id": "无改善公司", "news_count_before": 10, "news_links_after": 8},
    ]
}

out = processor.process(result, ctx)
print("有改善:", out["quality"]["companies_improved"])   # 1
print("无变化:", out["quality"]["companies_unchanged"])  # 2
print("总增量:", out["quality"]["total_increase"])       # 18
```

---

## 四、完整工作流（从CSV到验收报告的端到端）

```python
import asyncio, csv
from pathlib import Path
from core.company_news_crawler import CompanyRecord, run_batch

# ── 第1步：从CSV读入公司清单 ─────────────────────────────────────────────────
# CSV格式：公司名称,官网URL,新闻数量
companies = []
with open("低数量公司清单.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        companies.append(CompanyRecord(
            name=row["公司名称"],
            url=row["官网URL"],
            news_count_before=int(row.get("新闻数量", 0)),
        ))

print(f"读入 {len(companies)} 家公司")

# ── 第2步：批量抓取（断点可恢复）────────────────────────────────────────────
result = asyncio.run(run_batch(
    companies=companies,
    output_dir=Path("0407stage2_archive"),
    max_pages=20,
    batch_size=50,
    request_delay=0.5,
))

# ── 第3步：查看结果 ──────────────────────────────────────────────────────────
stats = result["crawl_stats"]
veri  = result["verification"]
print(f"成功: {stats['success_count']}, 失败: {stats['failed_count']}, 总页数: {stats['total_pages']}")
print(f"改善: {veri['improved']}, 无变化: {veri['unchanged']}, 缺失: {veri['missing']}")
print("详细验收报告已写入: 0407stage2_archive/verification_report.json")
```

---

## 五、环境变量配置（可选）

| 变量名 | 默认值 | 说明 |
|---|---|---|
| `WEB_ROOTER_CACHE_DB_PATH` | *(无)* | SQLite 缓存路径；设置后已抓 URL 不重复请求 |
| `WEB_ROOTER_JOB_RESULT_MAX_CHARS` | `220000` | job result 最大字符数 |
| `WEB_ROOTER_JOBS_MAX_COUNT` | `160` | jobs 目录最大保留数量 |
| `WEB_ROOTER_JOBS_MAX_AGE_DAYS` | `14` | jobs 自动清理天数 |
| `WEB_ROOTER_JOB_STALE_RUNNING_SEC` | `180` | 运行中 job 超时判定秒数 |

**启用 SQLite URL 缓存（推荐，避免重复抓取）：**

```bash
export WEB_ROOTER_CACHE_DB_PATH=./0407stage2_archive/.url_cache.db
```

---

## 六、常见问题

### Q: 程序运行到一半 Ctrl+C 了，下次怎么办？

**A:** 直接重新运行同样的脚本即可。检查点文件保存在 `output_dir/.checkpoints/`，启动时自动加载，已完成的公司会被自动跳过。

---

### Q: 某家公司一直失败（403 / Cloudflare），怎么处理？

**A:** 模块已内置浏览器 fallback（HTTP → Playwright headless）。如果仍失败，可单独对该公司调用 `crawl_news_pages(allow_browser=True)`。失败公司会记录在 `verification_report.json` 的 `missing_company_ids` 列表里。

---

### Q: 内存消耗过高怎么办？

**A:** `RuntimePressureController` 会自动监控内存：
- RSS > 600MB → elevated（减少每页HTML截取长度）
- RSS > 900MB → high（暂停5秒再继续）
- RSS > 1200MB → critical（关闭浏览器fallback，进一步降级）

如果仍有问题，可减小 `batch_size`（从50降到20）。

---

### Q: 如何只对失败的公司重跑？

**A:** 读取 `verification_report.json` 中的 `missing_company_ids`，筛选出对应的公司再重新执行：

```python
import json, asyncio
from pathlib import Path
from core.company_news_crawler import CompanyRecord, run_batch

report = json.loads(Path("0407stage2_archive/verification_report.json").read_text())
failed_ids = set(report["missing_company_ids"])

# 只取失败的公司（从原始清单过滤）
all_companies = [...]  # 完整309家
retry_companies = [c for c in all_companies if c.company_id in failed_ids]

print(f"重跑 {len(retry_companies)} 家失败公司")
asyncio.run(run_batch(retry_companies, output_dir=Path("0407stage2_archive")))
```

---

### Q: 如何运行测试验证环境是否正常？

```bash
python -m unittest tests.test_company_news_crawler -v
```

---

## 七、模块依赖关系（内部架构参考）

```
run_batch()
  └── CompanyNewsCrawler.run()
        ├── JobStore            → .web-rooter/jobs/<job_id>/meta.json
        ├── CheckpointManager   → output_dir/.checkpoints/*.pkl
        ├── ResultQueue         → 流式进度统计（内存内）
        ├── RuntimePressureController → 自适应内存保护
        ├── MemoryOptimizer     → 每批次结束 clear_temp_results()
        └── _process_company()
              └── crawl_news_pages()
                    ├── _fetch_html_http()   → aiohttp（UA轮换）
                    ├── _fetch_html_browser() → playwright headless（fallback）
                    ├── _extract_next_page_url() → BeautifulSoup rel=next
                    ├── _count_news_links()  → BeautifulSoup href匹配
                    ├── build_web_citations() → page_*.meta.json
                    └── crawl_summary.json
```
