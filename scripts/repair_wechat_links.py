"""把早先拼错的公众号链接清成空（内容留着，链接先不给）。

背景：2026-11-22 之前 `weread.parse_articles` 用的是 `mpInfo.originalId`，
那是微信读书自己包的一层（`WR1` 开头 76 位），拼成
`https://mp.weixin.qq.com/s/WR1...` 后打开一律「参数错误」。
真正的短链 token 在 `reviewId` 末段（22 位左右），代码已修；
这个脚本负责把库里已有的坏链先抹掉，别让人点到错页。

用法：
    python scripts/repair_wechat_links.py           # 只看
    python scripts/repair_wechat_links.py --apply   # 真改

改完重跑 run_daily.py，页面里这些条目会显示「来源 + 时间」但没有 ↗ 链接；
等微信读书 Cookie 续上、成功抓到文章后，`run_daily.py` 会自动
调用 `Store.drop_blank_urls()` 把这些占位行替换成带真链的新行。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ssdintel.models import Store  # noqa: E402

DB = Path(__file__).resolve().parent.parent / "data" / "ssdintel.db"
BAD = "mp.weixin.qq.com/s/WR"


def main() -> int:
    ap = argparse.ArgumentParser(description="清掉拼错的公众号链接")
    ap.add_argument("--apply", action="store_true", help="真的写库")
    args = ap.parse_args()

    store = Store(DB)
    rows = store.conn.execute(
        "SELECT uid, title FROM items WHERE url LIKE ?", (f"%{BAD}%",)
    ).fetchall()
    print(f"坏链条目：{len(rows)}")
    for _uid, title in rows[:10]:
        print("  -", (title or "")[:40])
    if not rows:
        return 0
    if not args.apply:
        print("\n（只看了，没改；加 --apply 才写库）")
        return 0

    n = 0
    for uid, _title in rows:
        store.conn.execute("UPDATE items SET url = '' WHERE uid = ?", (uid,))
        n += 1
    store.conn.commit()
    print(f"\n已把 {n} 条的 url 清空，重跑 run_daily.py 即可看到效果")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
