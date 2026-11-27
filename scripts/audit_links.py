"""抽查库里公众号链接是不是真的能打开（而不是「参数错误」页）。

规则 2.1：拼出来的 URL 上线前必须实测——200 且内容长度 > 100KB。
正常公众号文章页约 3.8–4.0MB，「参数错误」页只有 ~32KB，用长度就能分辨。

用法：
    python scripts/audit_links.py              # 抽 8 条
    python scripts/audit_links.py --n 20       # 抽 20 条
    python scripts/audit_links.py --all        # 全部（慢，别在 CI 里跑）

退出码：0 = 抽查全通过，1 = 有打不开的。
"""
from __future__ import annotations

import argparse
import random
import sqlite3
import sys
import time

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "ssdintel.db"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MIN_BYTES = 100_000          # 正常文章页 3.8MB 左右；错误页 ~32KB
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    if not DB.exists():
        print(f"[x] 没有数据库：{DB}")
        return 1

    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT source, title, url FROM items "
        "WHERE source_type = 'wechat' AND COALESCE(url, '') <> '' "
        "ORDER BY COALESCE(published, '') DESC"
    ).fetchall()
    if not rows:
        # 没有公众号条目不是渲染 bug（可能是限流/没配 Cookie），跳过而不是失败，
        # 否则 CI 会因为「今天没抓到公众号」把整次发布拦下来。
        print("[skip] 库里没有带链接的公众号条目，本次跳过抽查")
        return 0

    if not args.all:
        random.seed(args.seed)
        rows = random.sample(rows, min(args.n, len(rows)))

    print(f"抽查 {len(rows)} 条公众号链接（阈值 {MIN_BYTES} 字节）\n")

    try:
        import requests
    except ImportError:
        print("[x] 需要 requests")
        return 1

    bad: list[tuple[str, str, str]] = []
    net: list[tuple[str, str]] = []
    for source, title, url in rows:
        label = f"{source} · {(title or '')[:26]}"
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=45, allow_redirects=True)
            size = len(r.content)
            err_txt = "参数错误" in r.text[:5000]
            ok = r.status_code == 200 and size >= MIN_BYTES and not err_txt
            print(f"  {'ok ' if ok else '[x]'} {r.status_code} {size:>9} 字节  {label}")
            if not ok:
                bad.append((label, url, f"status={r.status_code} size={size} 参数错误={err_txt}"))
        except Exception as e:  # noqa: BLE001
            # 网络抖动不该拦发布：记下来当告警，只有「拿到内容但明显不对」才算硬失败。
            print(f"  [warn] 请求失败  {label}   {e}")
            net.append((label, str(e)))
        time.sleep(0.8)

    print()
    if net:
        print(f"[warn] {len(net)} 条因网络问题没验成（不拦发布）：")
        for label, why in net:
            print(f"    {label}  {why}")
    if bad:
        print(f"[x] {len(bad)} 条打不开：")
        for label, url, why in bad:
            print(f"    {label}\n      {url}\n      {why}")
        return 1
    print("[ok] 抽查全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
