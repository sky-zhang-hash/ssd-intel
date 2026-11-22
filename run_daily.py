#!/usr/bin/env python
"""SSD 情报日报 · 每日主流程。

用法：
    python run_daily.py                 # 抓 RSS + 搜狗微信，生成日报
    python run_daily.py --no-wechat     # 只抓 RSS（不碰搜狗，最稳）
    python run_daily.py --no-llm        # 不调模型，出原始清单
    python run_daily.py --hours 48      # 汇总最近 48 小时

环境变量：
    DEEPSEEK_API_KEY   可选。没有就走降级摘要，程序照常跑完。
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import yaml  # noqa: E402

from ssdintel import fetch, render, report as report_mod, score, weread  # noqa: E402
from ssdintel.models import Store  # noqa: E402


def load_yaml(path: Path) -> dict:
    if not path.exists():  # wechat_bookids.yaml 是跑完解析脚本才有的，允许缺失
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_env(path: Path) -> None:
    """极简 .env 读取：KEY=VALUE，忽略注释，不覆盖已有的环境变量。

    不引入 python-dotenv，就为省一个依赖——反正格式只有这么简单。
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    ap = argparse.ArgumentParser(description="SSD 情报日报")
    ap.add_argument("--no-wechat", action="store_true",
                    help="跳过公众号采集（等价于 --wechat-source off）")
    ap.add_argument("--wechat-source", choices=["auto", "weread", "sogou", "off"],
                    default="auto",
                    help="公众号来源：weread=微信读书（全量，推荐）/ "
                         "sogou=关键词搜索（旧路径，时效不佳）/ auto=有 Cookie 就用 weread")
    ap.add_argument("--no-llm", action="store_true", help="跳过 LLM，出原始清单")
    ap.add_argument("--hours", type=int, default=36, help="汇总最近多少小时（默认 36）")
    ap.add_argument("--pages", type=int, default=1, help="每个搜索词翻几页")
    ap.add_argument("--max-age", type=int, default=10,
                    help="丢弃发布超过多少天的条目（默认 10；0=不过滤）")
    ap.add_argument("--keep-days", type=int, default=60, help="库里保留多少天")
    ap.add_argument("--date", default=None, help="覆盖日报日期 YYYY-MM-DD")
    args = ap.parse_args()

    date = args.date or datetime.now().strftime("%Y-%m-%d")
    load_env(ROOT / ".env")
    cfg_dir = ROOT / "config"
    sources = load_yaml(cfg_dir / "sources.yaml").get("sources", [])
    wx_cfg = load_yaml(cfg_dir / "wechat_accounts.yaml")
    bookid_cfg = load_yaml(cfg_dir / "wechat_bookids.yaml")
    rules = score.load_rules(str(cfg_dir / "keywords.yaml"))

    store = Store(ROOT / "data" / "ssdintel.db")

    # ---------------- 采集 ----------------
    print(f"\n== 采集 · {date} ==")
    session = fetch.new_session()
    rss_items, rss_health = fetch.fetch_rss(sources, session=session)

    # 公众号来源：weread 需要 Cookie + 解析好的 bookId，缺一不可
    cookie = os.environ.get("WEREAD_COOKIE", "").strip()
    book_ids = {a["name"]: a["book_id"] for a in bookid_cfg.get("accounts") or []
                if a.get("name") and a.get("book_id")}
    mode = "off" if args.no_wechat else args.wechat_source
    if mode == "auto":
        # 没 Cookie 就不碰公众号：搜狗那条路实测只返回 30 天前的旧文，
        # 自动降级过去纯属浪费时间，还会平白多一次反爬。要用显式 --wechat-source sogou。
        mode = "weread" if (cookie and book_ids) else "off"
        if mode == "off":
            print("  [wx]  没有 WEREAD_COOKIE / bookId，本次跳过公众号"
                  "（见 .env.example 与 scripts/resolve_bookids.py）")

    wx_items, wx_health = [], []
    if mode == "weread":
        if not cookie:
            print("  [wx]  没有 WEREAD_COOKIE，跳过（见 .env.example）")
        elif not book_ids:
            print("  [wx]  还没解析 bookId，先跑 scripts/resolve_bookids.py，跳过")
        else:
            print(f"  公众号：微信读书 · {len(book_ids)} 个号")
            wx_items, wx_health = weread.collect(
                book_ids, cookie, pages=args.pages
            )
    elif mode == "sogou":
        queries = wx_cfg.get("search_queries", [])
        if queries:
            print(f"  公众号：搜狗关键词 · {len(queries)} 个词")
            wx_items, wx_health = fetch.collect_wechat(
                queries, session=session, pages=args.pages
            )

    raw = rss_items + wx_items
    print(f"\n  原始 {len(raw)} 条（RSS {len(rss_items)} / 微信 {len(wx_items)}）")

    # ---------------- 打分 ----------------
    scored = score.apply(raw, rules)
    fresh_scored = score.filter_fresh(scored, args.max_age)
    dropped_old = len(scored) - len(fresh_scored)
    deduped = score.dedupe(fresh_scored)
    print(f"  过线 {len(scored)} 条，过时丢弃 {dropped_old} 条，"
          f"跨源去重后 {len(deduped)} 条")

    # 只还原要上日报的那几条真链，别每条都打一次搜狗
    deduped = fetch.resolve_items(deduped, session=session)

    added = store.upsert_items(deduped)
    store.log_health(rss_health + wx_health)
    print(f"  新增入库 {added} 条")

    # ---------------- 汇总 ----------------
    fresh = store.recent(hours=args.hours)
    print(f"  最近 {args.hours}h 共 {len(fresh)} 条可汇总")

    # ---------------- 生成 ----------------
    print("\n== 生成日报 ==")
    api_key = None if args.no_llm else os.environ.get("DEEPSEEK_API_KEY")
    payload = report_mod.build(fresh, date=date, api_key=api_key)

    stats = {
        "items": len(fresh),
        "sources": len({it.source for it in fresh}),
        "raw": len(raw),
    }
    index = render.render(payload, ROOT / "web", stats=stats)
    store.save_report(date, payload, index.read_text(encoding="utf-8"))

    store.purge_old(args.keep_days)
    print(f"\n完成：{index}")
    print(f"库内统计：{store.stats()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
