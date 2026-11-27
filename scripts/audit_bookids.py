"""核对 config/wechat_bookids.yaml 里的名字和 bookId 到底是不是同一个号。

规则 1.1：名字→ID 的映射必须用服务端返回的权威名字反向核对，不一致就报错退出。
微信读书的 /api/mp/cover 会回 name，这是最便宜且不需要文章列表配额的身份检查。

用法：
    python scripts/audit_bookids.py            # 全量核对
    python scripts/audit_bookids.py --limit 5  # 只看前 5 个（调试用）

退出码：0 = 全部一致（允许「包含关系」），1 = 有不一致或取不到。
"""
from __future__ import annotations

import argparse
import io
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from ssdintel import weread  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load_cookie() -> str:
    """优先 .env，其次 collector 抓到的 cookie.txt。"""
    for rel in (".env", "collector/data/cookie.txt"):
        p = ROOT / rel
        if not p.exists():
            continue
        text = io.open(p, encoding="utf-8").read()
        if rel.endswith(".txt"):
            c = text.strip()
            if c:
                return c
        for line in text.splitlines():
            if line.startswith("WEREAD_COOKIE="):
                c = line.split("=", 1)[1].strip()
                if c:
                    return c
    return ""


def same(a: str, b: str) -> bool:
    a = a.replace("公众号", "").replace(" ", "").strip()
    b = b.replace("公众号", "").replace(" ", "").strip()
    return a == b or a in b or b in a


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=1.2)
    args = ap.parse_args()

    cfg_path = ROOT / "config" / "wechat_bookids.yaml"
    cfg = yaml.safe_load(io.open(cfg_path, encoding="utf-8").read()) or {}
    accounts = cfg.get("accounts") or []
    if not accounts:
        print("[x] config/wechat_bookids.yaml 里没有 accounts")
        return 1

    cookie = load_cookie()
    if not cookie:
        print("[x] 找不到 WEREAD_COOKIE（.env 或 collector/data/cookie.txt）")
        return 1
    print(f"cookie 长度 {len(cookie)}；核对 {len(accounts)} 个号\n")

    session = weread.new_session(cookie)
    if args.limit:
        accounts = accounts[: args.limit]

    bad: list[tuple[str, str, str]] = []
    err: list[tuple[str, str]] = []
    for acc in accounts:
        name, bid = str(acc.get("name")), str(acc.get("book_id"))
        try:
            payload = weread._get(session, "/api/mp/cover", {"bookId": bid}, timeout=20, retries=2)
        except weread.WereadError as e:
            err.append((name, f"{e.code} {e}"))
            print(f"  {name:16} 取不到：{e.code}")
            continue
        real = str(payload.get("name") or "")
        if not real:
            err.append((name, "返回里没有 name 字段"))
            print(f"  {name:16} 返回没有 name 字段")
        elif same(name, real):
            print(f"  {name:16} -> {real}  ok")
        else:
            bad.append((name, bid, real))
            print(f"  {name:16} -> {real}   <-- 名字不符")
        time.sleep(args.sleep)

    print()
    if bad:
        print(f"[x] {len(bad)} 个号名字不符，必须修正配置后再上线：")
        for name, bid, real in bad:
            print(f"    {name} ({bid}) 实际是「{real}」")
    if err:
        print(f"[!] {len(err)} 个号这颗接口取不到（可能是限流，稍后重跑）：")
        for name, why in err:
            print(f"    {name}: {why}")

    if bad:
        return 1
    if err:
        # 取不到不等于错，但也不能当作通过
        return 1
    print("[ok] 全部一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
