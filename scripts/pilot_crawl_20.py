"""
pilot_crawl_20.py — 前20家公司新闻中心试抓脚本

用法：
    # 用内置的20家样本公司（测试用）
    python scripts/pilot_crawl_20.py

    # 从你自己的 CSV 读入（格式：公司名称,官网URL,新闻数量）
    python scripts/pilot_crawl_20.py --csv D:/newagent/workflow/低数量公司清单.csv

    # 指定输出目录和每家公司的最大抓取页数
    python scripts/pilot_crawl_20.py --csv 低数量公司清单.csv --output 0407stage2_archive --max-pages 5

输出：
    <output_dir>/
    ├── <公司ID>/
    │   ├── page_0001.html
    │   ├── page_0001.meta.json
    │   └── crawl_summary.json
    └── verification_report.json
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import sys
from pathlib import Path

# ── 确保项目根目录在 sys.path ────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.company_news_crawler import CompanyRecord, run_batch  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pilot_crawl_20")

# ---------------------------------------------------------------------------
# 内置样本公司（当用户未提供 CSV 时使用，均为公开企业官网新闻页）
# ---------------------------------------------------------------------------
_SAMPLE_COMPANIES: list[dict] = [
    # name, url, news_count_before
    {"name": "华为技术",        "url": "https://www.huawei.com/cn/news",                   "before": 5},
    {"name": "小米集团",        "url": "https://www.mi.com/about/news",                    "before": 3},
    {"name": "联想集团",        "url": "https://news.lenovo.com/zh-hans/",                 "before": 4},
    {"name": "中兴通讯",        "url": "https://www.zte.com.cn/china/about/news_events/",  "before": 2},
    {"name": "比亚迪",          "url": "https://www.byd.com/cn/news.html",                 "before": 6},
    {"name": "宁德时代",        "url": "https://www.catlbattery.com/news",                 "before": 1},
    {"name": "美的集团",        "url": "https://www.midea.com/cn/About-Midea/Media",       "before": 3},
    {"name": "格力电器",        "url": "https://www.gree.com/news/",                       "before": 2},
    {"name": "海尔集团",        "url": "https://www.haier.com/cn/news/",                   "before": 4},
    {"name": "TCL科技",         "url": "https://www.tcl.com/cn/zh/company/news.html",      "before": 1},
    {"name": "京东方",          "url": "https://www.boe.com/zh-cn/news/",                  "before": 5},
    {"name": "吉利汽车",        "url": "https://www.geely.com/cn/news",                    "before": 3},
    {"name": "长安汽车",        "url": "https://www.changan.com.cn/news/",                 "before": 2},
    {"name": "三一重工",        "url": "https://www.sany.com.cn/oa/news/",                 "before": 4},
    {"name": "中联重科",        "url": "https://www.zoomlion.com/cn/index.html",           "before": 1},
    {"name": "海康威视",        "url": "https://www.hikvision.com/cn/newsroom/",           "before": 6},
    {"name": "大疆创新",        "url": "https://www.dji.com/cn/newsroom",                  "before": 2},
    {"name": "科大讯飞",        "url": "https://www.iflytek.com/about/index.html",         "before": 3},
    {"name": "商汤科技",        "url": "https://www.sensetime.com/cn/news-detail",         "before": 1},
    {"name": "旷视科技",        "url": "https://www.megvii.com/news",                      "before": 2},
]


def load_companies_from_csv(csv_path: str, limit: int = 20) -> list[CompanyRecord]:
    """从 CSV 文件读入公司列表（取前 limit 家）。

    CSV 格式（有表头）：
        公司名称,官网URL,新闻数量
    """
    records: list[CompanyRecord] = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if len(records) >= limit:
                break
            # 兼容多种列名
            name = row.get("公司名称") or row.get("name") or row.get("company") or ""
            url  = row.get("官网URL")  or row.get("url")  or row.get("website") or ""
            before_str = row.get("新闻数量") or row.get("news_count_before") or "0"
            if not name or not url:
                logger.warning("跳过空行: %s", row)
                continue
            try:
                before = int(str(before_str).strip())
            except ValueError:
                before = 0
            records.append(CompanyRecord(name=name.strip(), url=url.strip(), news_count_before=before))
    logger.info("从 CSV 读入 %d 家公司（前 %d 家）", len(records), limit)
    return records


def load_sample_companies() -> list[CompanyRecord]:
    """使用内置样本公司（20家）。"""
    records = [
        CompanyRecord(name=c["name"], url=c["url"], news_count_before=c["before"])
        for c in _SAMPLE_COMPANIES
    ]
    logger.info("使用内置样本公司，共 %d 家", len(records))
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="前20家公司新闻中心试抓脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--csv", default=None,
        help="公司清单 CSV 路径（格式：公司名称,官网URL,新闻数量）。不传则使用内置样本公司。",
    )
    parser.add_argument(
        "--output", default="0407stage2_archive",
        help="输出目录（默认：0407stage2_archive）",
    )
    parser.add_argument(
        "--max-pages", type=int, default=3,
        help="每家公司最多抓取页数（默认：3，正式运行时改为 20）",
    )
    parser.add_argument(
        "--delay", type=float, default=0.5,
        help="请求间隔秒数（默认：0.5）",
    )
    parser.add_argument(
        "--limit", type=int, default=20,
        help="从 CSV 读入的公司数量上限（默认：20）",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    # 加载公司列表
    if args.csv:
        companies = load_companies_from_csv(args.csv, limit=args.limit)
    else:
        companies = load_sample_companies()

    if not companies:
        logger.error("公司列表为空，退出")
        sys.exit(1)

    output_dir = Path(args.output)
    logger.info(
        "开始试抓 — 公司数=%d, 每家最多%d页, 输出目录=%s",
        len(companies), args.max_pages, output_dir,
    )

    result = await run_batch(
        companies=companies,
        output_dir=output_dir,
        max_pages=args.max_pages,
        batch_size=20,         # 20家全部在一批里
        request_delay=args.delay,
    )

    # 打印摘要
    stats = result.get("crawl_stats", {})
    veri  = result.get("verification", {})
    print()
    print("=" * 60)
    print("  试抓完成")
    print("=" * 60)
    print(f"  总公司数   : {len(companies)}")
    print(f"  成功       : {stats.get('success_count', '—')}")
    print(f"  失败       : {stats.get('failed_count', '—')}")
    print(f"  总抓取页数 : {stats.get('total_pages', '—')}")
    print()
    print(f"  新闻有增加 : {veri.get('improved', '—')} 家")
    print(f"  无变化     : {veri.get('unchanged', '—')} 家")
    print(f"  缺失结果   : {veri.get('missing', '—')} 家")
    print()
    print(f"  详细验收报告: {output_dir}/verification_report.json")
    print("=" * 60)

    # 打印失败公司
    if veri.get("missing_company_ids"):
        print("\n  ⚠️  以下公司未能抓取：")
        for cid in veri["missing_company_ids"]:
            print(f"    - {cid}")

    # 打印改善最多的前5家
    improved = veri.get("improved_companies", [])
    if improved:
        top5 = sorted(improved, key=lambda x: x["increase"], reverse=True)[:5]
        print("\n  ✅ 新闻增量最多的前5家：")
        for entry in top5:
            print(f"    {entry['company_name']}: {entry['news_count_before']} → "
                  f"{entry['news_links_after']} (+{entry['increase']})")

    print()


if __name__ == "__main__":
    asyncio.run(main())
