#!/usr/bin/env python
"""从微信读书「书架」里把已关注的公众号 bookId 批量读出来。

做法：你在微信读书 App 里搜这几个公众号 → 关注（会进书架）→ 然后跑这个脚本，
它会调 /web/shelf/sync 把书架上的 `MP_WXS_*` 全部列出来并写进
config/wechat_bookids.yaml，不用一个个复制文章链接。

用法：
    python scripts\\shelf_bookids.py              # 读书架，自动匹配公众号清单
    python scripts\\shelf_bookids.py --dry-run    # 只打印，不写文件
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import yaml  # noqa: E402

from ssdintel import weread  # noqa: E402


def load_env(path: Path) -> None:
    import os
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def norm(s: str) -> str:
    """书架上的名字常和清单差一点：多空格、全角、多了后缀。归一化再比。"""
    s = s.replace("　", "").replace(" ", "")
    for a, b in (("（", "("), ("）", ")"), ("・", ""), ("·", ""), ("-", "")):
        s = s.replace(a, b)
    return s.strip().lower()


def match(name: str, wanted: list[str]) -> str:
    """书架名 → 清单里的标准名；认不出返回空。"""
    n = norm(name)
    for w in wanted:
        if norm(w) == n:
            return w
    # 一边包含另一边也算（「HOMOLAB 存储狂热」vs「HOMOLAB存储狂热」、
    # 「长江存储商用存储方案」vs「长江存储」、「闪德资讯」vs「闪德咨讯」）
    for w in wanted:
        nw = norm(w)
        if len(nw) >= 3 and (nw in n or n in nw):
            return w
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_env(ROOT / ".env")
    import os
    cookie = os.environ.get("WEREAD_COOKIE", "").strip()
    if not cookie:
        print("✗ .env 里没有 WEREAD_COOKIE")
        return 1

    s = weread.new_session(cookie)
    payload = weread._get(s, "/web/shelf/sync", {}, timeout=25)
    books = payload.get("books") or []
    print(f"书架上有 {len(books)} 项")

    found: dict[str, str] = {}
    other = 0
    for b in books:
        bid = b.get("bookId") or ""
        if not bid.startswith("MP_WXS_"):
            other += 1
            continue
        name = (b.get("title") or "").strip()
        found[name] = bid
        print(f"  {name:<20} {bid}")
    if other:
        print(f"  （另外 {other} 项是电子书/有声书，跳过）")

    if not found:
        print("书架里没有公众号。在微信读书 App 里搜公众号名并关注，再跑一次。")
        return 1

    # 和关注清单对齐
    with open(ROOT / "config" / "wechat_accounts.yaml", encoding="utf-8") as f:
        wx = yaml.safe_load(f) or {}
    wanted = [a if isinstance(a, str) else a.get("name") for a in wx.get("accounts", [])]
    wanted = [n for n in wanted if n]

    dest = ROOT / "config" / "wechat_bookids.yaml"
    data = {}
    if dest.exists():
        with open(dest, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    accounts = {a["name"]: a["book_id"] for a in (data.get("accounts") or [])
                if a.get("name") and a.get("book_id")}

    added = 0
    for name, bid in found.items():
        target = match(name, wanted)
        if target:
            if accounts.get(target) != bid:
                accounts[target] = bid
                added += 1
                print(f"  + {target} → {bid}" + ("" if target == name else f"（书架名「{name}」）"))
        else:
            print(f"  · 书架上有「{name}」，但不在关注清单里，跳过")

    missing = [n for n in wanted if n not in accounts]
    print(f"\n已解析 {len(accounts)}/{len(wanted)} 个号")
    if missing:
        print("还缺：" + "、".join(missing))

    if args.dry_run:
        print("\n（--dry-run，没有写文件）")
        return 0

    with open(dest, "w", encoding="utf-8") as f:
        yaml.safe_dump({
            "note": "由 scripts/shelf_bookids.py 或 resolve_bookids.py 生成：微信读书的公众号 bookId",
            "accounts": [{"name": k, "book_id": v} for k, v in accounts.items()],
            "missing": missing,
        }, f, allow_unicode=True, sort_keys=False)
    print(f"写入 {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
