#!/usr/bin/env python
"""看一眼库里现在有什么。开发调试用。

用法：
    python scripts/inspect_db.py            # 分数最高的 25 条
    python scripts/inspect_db.py --by-source # 按源统计
    python scripts/inspect_db.py --health   # 最近一次采集各源状态
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--by-source", action="store_true")
    ap.add_argument("--health", action="store_true")
    ap.add_argument("--limit", type=int, default=25)
    args = ap.parse_args()

    db = ROOT / "data" / "ssdintel.db"
    if not db.exists():
        print(f"还没有库：{db}\n先跑一次 python run_daily.py --no-llm")
        return 1
    c = sqlite3.connect(db)

    if args.health:
        print(f"{'源':<24}{'状态':<8}{'条数':<6}说明")
        print("-" * 78)
        for name, ok, count, detail in c.execute(
            """SELECT name, ok, count, detail FROM health
               WHERE ts = (SELECT MAX(ts) FROM health) ORDER BY ok, name"""
        ):
            print(f"{name:<24}{'OK' if ok else 'FAIL':<8}{count:<6}{detail[:34]}")
        return 0

    if args.by_source:
        print(f"{'源':<24}{'条数':<8}{'均分':<8}{'最高'}")
        print("-" * 60)
        for row in c.execute(
            """SELECT source, COUNT(*), ROUND(AVG(score),2), ROUND(MAX(score),2)
               FROM items GROUP BY source ORDER BY 2 DESC"""
        ):
            print(f"{row[0]:<24}{row[1]:<8}{row[2]:<8}{row[3]}")
        return 0

    print(f"{'分':<6}{'源':<16}{'类别':<18}标题")
    print("-" * 100)
    for score, src, cats, title in c.execute(
        """SELECT score, source, categories, title FROM items
           ORDER BY score DESC, published DESC LIMIT ?""", (args.limit,)
    ):
        cat = ",".join(json.loads(cats or "[]"))[:16]
        print(f"{score:<6.2f}{src[:15]:<16}{cat:<18}{title[:64]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
