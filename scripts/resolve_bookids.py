#!/usr/bin/env python
"""把公众号 → 微信读书 bookId，写进 config/wechat_bookids.yaml。

原理：微信读书的 bookId = "MP_WXS_" + base64解码(公众号的 __biz)。
__biz 写在公众号**任意一篇文章**里，是公开信息 —— 但要注意两种链接：

  https://mp.weixin.qq.com/s/AbCdEf...        短链，页面里有 var biz="..."   ✅ 能用
  https://mp.weixin.qq.com/s?src=11&signature=...   搜狗签名的链接，会撞验证码  ❌ 别用

所以最省事的办法是：在手机上打开该公众号任意一篇文章 → 右上角 ⋯ → 复制链接 →
把链接发过来。一个号一条，给多少解析多少，剩下的以后随时补。

用法：
    python scripts\\resolve_bookids.py --link "闪存市场=https://mp.weixin.qq.com/s/xxx"
    python scripts\\resolve_bookids.py --links links.txt      # 每行 号名=链接 或 只写链接
    python scripts\\resolve_bookids.py --list                 # 看已经解析出哪些
"""
from __future__ import annotations

import argparse
import base64
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests  # noqa: E402
import yaml  # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
DEST = ROOT / "config" / "wechat_bookids.yaml"


def book_id_from_biz(biz: str) -> str | None:
    s = (biz or "").replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    try:
        raw = base64.b64decode(s)
    except Exception:
        return None
    digits = re.sub(r"[^0-9]", "", raw.decode("utf-8", "ignore"))
    return f"MP_WXS_{digits}" if 5 <= len(digits) <= 15 else None


def biz_from_html(html: str) -> str | None:
    for pat in (r'var\s+biz\s*=\s*["\']([A-Za-z0-9+/=_-]+)["\']',
                r'__biz["\']?\s*[:=]\s*["\']([A-Za-z0-9+/=_-]+)["\']',
                r'[?&]__biz=([A-Za-z0-9+/=_-]+)'):
        m = re.search(pat, html or "")
        if m:
            return m.group(1)
    return None


def resolve(url: str, session: requests.Session) -> tuple[str | None, str]:
    """返回 (bookId, 说明)。"""
    if "__biz=" in url:  # 链接里直接带，不用联网
        bid = book_id_from_biz(url.split("__biz=")[1].split("&")[0])
        return bid, "从链接里的 __biz 直接解出" if bid else "__biz 解码失败"
    try:
        r = session.get(url, timeout=25)
    except requests.RequestException as e:
        return None, f"抓取失败 {type(e).__name__}"
    if "wappoc_appmsgcaptcha" in r.url or "验证" in r.text[:3000]:
        return None, "撞到微信验证码（搜狗签名链接常见），换一条原始短链"
    biz = biz_from_html(r.text)
    if not biz:
        return None, f"页面里没找到 __biz（{len(r.text)}B）"
    bid = book_id_from_biz(biz)
    return bid, f"__biz={biz}" if bid else f"__biz={biz} 解码失败"


def load() -> dict:
    if DEST.exists():
        with open(DEST, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {"accounts": [], "missing": []}


def save(data: dict) -> None:
    rows, seen = [], set()
    for a in data.get("accounts") or []:
        if a.get("name") and a.get("book_id") and a["name"] not in seen:
            seen.add(a["name"])
            rows.append({"name": a["name"], "book_id": a["book_id"]})
    out = {
        "note": "由 scripts/resolve_bookids.py 生成：微信读书的公众号 bookId",
        "accounts": rows,
        "missing": data.get("missing") or [],
    }
    with open(DEST, "w", encoding="utf-8") as f:
        yaml.safe_dump(out, f, allow_unicode=True, sort_keys=False)


def main() -> int:
    ap = argparse.ArgumentParser(description="解析公众号 bookId")
    ap.add_argument("--link", action="append", default=[],
                    help='号名=链接，可重复；只给链接则从公众号配置里按顺序推名字')
    ap.add_argument("--links", default=None, help="从文件读，每行 号名=链接")
    ap.add_argument("--list", action="store_true", help="只看已有的解析结果")
    args = ap.parse_args()

    data = load()
    if args.list:
        rows = data.get("accounts") or []
        print(f"已解析 {len(rows)} 个：")
        for a in rows:
            print(f"  {a['name']:<18} {a['book_id']}")
        if data.get("missing"):
            print("未解析：" + "、".join(data["missing"]))
        return 0

    pairs: list[tuple[str, str]] = []
    for item in args.link:
        if "=" in item:
            name, url = item.split("=", 1)
            pairs.append((name.strip(), url.strip()))
        else:
            pairs.append(("", item.strip()))
    if args.links:
        for line in Path(args.links).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                n, u = line.split("=", 1)
                pairs.append((n.strip(), u.strip()))
            else:
                pairs.append(("", line))
    if not pairs:
        ap.print_help()
        return 1

    # 没写名字的，按公众号清单顺序补
    with open(ROOT / "config" / "wechat_accounts.yaml", encoding="utf-8") as f:
        wx = yaml.safe_load(f) or {}
    known = [a if isinstance(a, str) else a.get("name") for a in wx.get("accounts", [])]
    known = [n for n in known if n]
    pairs = [(n or (known[i] if i < len(known) else ""), u)
             for i, (n, u) in enumerate(pairs)]

    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})

    ok = 0
    for name, url in pairs:
        bid, why = resolve(url, session)
        if bid:
            data["accounts"] = [a for a in (data.get("accounts") or [])
                                if a.get("name") != name]
            data["accounts"].append({"name": name, "book_id": bid})
            ok += 1
            print(f"  ✅ {name or '(未命名)':<16} {bid}   {why}")
        else:
            print(f"  ❌ {name or '(未命名)':<16} {why}")
            if name and name not in (data.get("missing") or []):
                data.setdefault("missing", []).append(name)

    save(data)
    print(f"\n成功 {ok}/{len(pairs)}，写入 {DEST}")
    print("下一句就能验证：python run_daily.py --no-llm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
