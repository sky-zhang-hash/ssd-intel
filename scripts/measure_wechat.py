#!/usr/bin/env python
"""量化搜狗微信采集的「时效性」——它到底能不能撑起一份每日日报。

搜狗微信文章搜索只按相关度排序（tsn=1 时间排序参数实测失效，返回落地页），
所以结果里混着大量几年前的经典文章。这个脚本就是用来量清楚：

    python scripts/measure_wechat.py            # 默认每词 3 页
    python scripts/measure_wechat.py --pages 5

输出每个搜索词的「新鲜度分布」：7 天内 / 30 天内 / 更旧。
这决定了公众号这一路是只能当补充，还是必须上 WeRSS。
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import yaml  # noqa: E402

from ssdintel import fetch  # noqa: E402


def age_days(published: str) -> float | None:
    if not published:
        return None
    try:
        dt = datetime.fromisoformat(published)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=3)
    args = ap.parse_args()

    with open(ROOT / "config" / "wechat_accounts.yaml", encoding="utf-8") as f:
        queries = yaml.safe_load(f).get("search_queries", [])

    session = fetch.new_session()
    bucket = Counter()
    per_query = []
    accounts = Counter()

    for q in queries:
        fresh7 = fresh30 = old = unknown = 0
        for p in range(1, args.pages + 1):
            items, health = fetch.search_wechat(q, session=session, page=p)
            for it in items:
                accounts[it.source] += 1
                d = age_days(it.published)
                if d is None:
                    unknown += 1
                elif d <= 7:
                    fresh7 += 1
                elif d <= 30:
                    fresh30 += 1
                else:
                    old += 1
            if not items:
                break
        per_query.append((q, fresh7, fresh30, old, unknown))
        bucket["7d"] += fresh7
        bucket["30d"] += fresh30
        bucket["old"] += old
        bucket["unknown"] += unknown
        print(f"{q:<20} 7天内 {fresh7:>3} | 30天内 {fresh30:>3} | 更旧 {old:>3} | 无日期 {unknown:>3}")

    total = sum(bucket.values())
    print("\n" + "=" * 60)
    print(f"合计 {total} 条")
    if total:
        for k, label in (("7d", "7 天内"), ("30d", "8-30 天"), ("old", "30 天以上")):
            print(f"  {label:<10} {bucket[k]:>4} 条  {bucket[k] / total * 100:>5.1f}%")
        print(f"  {'无日期':<10} {bucket['unknown']:>4} 条")

    print("\n出现最多的公众号（前 12）：")
    for name, n in accounts.most_common(12):
        print(f"  {name:<22}{n}")
    print("\n关注清单里命中过的号：")
    with open(ROOT / "config" / "wechat_accounts.yaml", encoding="utf-8") as f:
        wanted = [a["name"] for a in yaml.safe_load(f).get("accounts", [])]
    hit = [w for w in wanted if any(w in k or k in w for k in accounts)]
    miss = [w for w in wanted if w not in hit]
    print(f"  命中 {len(hit)}/{len(wanted)}: {', '.join(hit) or '无'}")
    print(f"  未命中: {', '.join(miss) or '无'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
