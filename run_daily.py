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
from datetime import datetime, timedelta, timezone
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


WEEKDAY = "一二三四五六日"


CST = timezone(timedelta(hours=8))


def local_day(iso: str) -> tuple[str, str]:
    """(排序键, 显示标签)：("2026-11-22", "11月22日 周六")。"""
    if not iso:
        return "", "日期未知"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(CST)
    except ValueError:
        return iso[:10], iso[:10]
    return dt.strftime("%Y-%m-%d"), f"{dt.month}月{dt.day}日 周{WEEKDAY[dt.weekday()]}"


def group_by_day(items, date_str: str) -> list[dict]:
    """「全部」页用：按本地日期分组，组内按时间倒序。"""
    buckets: dict[tuple[str, str], list] = {}
    for it in items:
        buckets.setdefault(local_day(it.published), []).append(it)
    groups = []
    for key, label in sorted(buckets, key=lambda k: k[0], reverse=True):
        rows = sorted(buckets[(key, label)], key=lambda x: x.published or "", reverse=True)
        groups.append({
            "date": key or label,
            "label": label,
            "rows": [{
                "title": it.title,
                # 只放绝对地址；认不出来的（比如历史坏数据）当"没有链接"处理
                "url": it.url if (it.url or "").startswith("http") else "",
                "source": it.source,
                "time": report_mod.local_time(it.published, date_str),
                "cats": list(it.categories or []),
            } for it in rows],
        })
    return groups


def main() -> int:
    ap = argparse.ArgumentParser(description="SSD 情报日报")
    ap.add_argument("--no-wechat", action="store_true",
                    help="跳过公众号采集（等价于 --wechat-source off）")
    ap.add_argument("--wechat-source", choices=["auto", "weread", "sogou", "off"],
                    default="auto",
                    help="公众号来源：weread=微信读书（全量，推荐）/ "
                         "sogou=关键词搜索（旧路径，时效不佳）/ auto=有 Cookie 就用 weread")
    ap.add_argument("--no-llm", action="store_true", help="跳过 LLM，出原始清单")
    ap.add_argument("--hours", type=int, default=168,
                    help="汇总最近多少小时（默认 168 = 近一周）")
    ap.add_argument("--pages", type=int, default=1, help="每个搜索词翻几页")
    ap.add_argument("--max-age", type=int, default=10,
                    help="丢弃发布超过多少天的条目（默认 10；0=不过滤）")
    ap.add_argument("--keep-days", type=int, default=60, help="库里保留多少天")
    ap.add_argument("--date", default=None, help="覆盖日报日期 YYYY-MM-DD")
    args = ap.parse_args()

    date = args.date or datetime.now(CST).strftime("%Y-%m-%d")
    load_env(ROOT / ".env")
    cfg_dir = ROOT / "config"
    sources = load_yaml(cfg_dir / "sources.yaml").get("sources", [])
    wx_cfg = load_yaml(cfg_dir / "wechat_accounts.yaml")
    bookid_cfg = load_yaml(cfg_dir / "wechat_bookids.yaml")
    rules = score.load_rules(str(cfg_dir / "keywords.yaml"))

    store = Store(ROOT / "data" / "ssdintel.db")

    # 规则 2.4：站内相对路径的历史行补成绝对地址（CI 的缓存库里可能还留着旧数据）
    bases = {}
    for s in sources:
        u = (s.get("url") or "").strip()
        if u.startswith("http"):
            bases[s.get("name", "")] = "/".join(u.split("/")[:3])
    fixed = store.fix_relative_urls(bases)
    if fixed:
        print(f"  修好 {fixed} 条站内相对路径链接")

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
            # 先看 keeper 有没有导出快照：Node fetch 能过 -2041，Python requests 过不了，
            # 所以浏览器在跑的时候，这条路径比我们自己去拉更可靠。
            snap_path = ROOT / "data" / "wechat_latest.json"
            snap_items, snap_health, snap_meta = weread.load_snapshot(
                snap_path, cookie=cookie
            )
            if snap_items:
                print(f"  公众号：keeper 快照 · {len(snap_items)} 篇 / "
                      f"{snap_meta.get('accounts')} 个号（抓于 {snap_meta.get('fetched_at')}，"
                      f"{snap_meta.get('age_h')} 小时前）")
                wx_items, wx_health = snap_items, snap_health
            else:
                if snap_meta.get("reason") not in ("no-file",):
                    print(f"  [wx]  快照不可用（{snap_meta.get('reason')}），改走接口")
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

    # 老版本用 originalId 拼的公众号链接一律「参数错误」，先清空（幂等）
    if store.blank_bad_wechat_urls():
        print("  清掉了早先拼错的公众号链接")
    added = store.upsert_items(deduped)
    if wx_items:  # 这轮真抓到公众号文章了，说明占位行（url 空）可以退休
        cleaned = store.drop_blank_urls()
        if cleaned:
            print(f"  清掉 {cleaned} 条没有原文链接的占位行")
    else:
        # 文章列表拿不到（限流或 Cookie 失效）时，/api/mp/cover 不需要登录还能用：
        # 每个号取最新一篇，既补链接、也直接当今天的公众号条目，免得整个板块空着。
        if mode == "weread" and book_ids:
            try:
                by_title = weread.cover_links(book_ids, cookie)
                filled = store.fill_missing_urls(by_title)
                if filled:
                    print(f"  用 cover 兜底补回 {filled} 条公众号原文链接")
                wx_items = weread.cover_items(book_ids, cookie)
                if wx_items:
                    print(f"  用 cover 兜底取到 {len(wx_items)} 个号的最新一篇")
                    scored = score.apply(raw + wx_items, rules)
                    fresh_scored = score.filter_fresh(scored, args.max_age)
                    deduped = score.dedupe(fresh_scored)
                    added = store.upsert_items(deduped)
            except Exception as e:  # 兜底失败不影响主流程
                print(f"  [wx]  cover 兜底失败：{e}")
    store.log_health(rss_health + wx_health)
    print(f"  新增入库 {added} 条")

    # ---------------- 汇总 ----------------
    fresh = store.recent(hours=args.hours)
    # 没有原文链接的条目不进日报：读者点不动的东西不如不给。
    # （公众号链接靠 Cookie 抓，失效期间冒出来的占位行会被这里挡掉。）
    with_link = [it for it in fresh if it.url]
    if len(with_link) < len(fresh):
        print(f"  跳过 {len(fresh) - len(with_link)} 条没有原文链接的旧条目")
    fresh = with_link
    print(f"  最近 {args.hours}h 共 {len(fresh)} 条可汇总")

    # ---------------- 生成 ----------------
    print("\n== 生成日报 ==")
    api_key = None if args.no_llm else os.environ.get("DEEPSEEK_API_KEY")
    payload = report_mod.build(fresh, date=date, api_key=api_key)

    # 公众号授权失效时，页面顶部要明说，不要让人以为「这些源没新闻」
    auth_down = [h for h in wx_health
                 if not h.get("ok") and ("2012" in str(h.get("error", ""))
                                        or "Cookie" in str(h.get("error", "")))]
    if auth_down:
        if wx_items:
            payload["warn"] = (f"公众号文章列表被微信读书限流：本次走封面兜底，"
                               f"只取到 {len(wx_items)} 个号的最新一篇"
                               f"（链接和正文都能点，只是每个号只一篇）。"
                               f"配额恢复后会自动回到全量。")
        else:
            payload["warn"] = ("微信读书登录态失效：公众号文章一条都没抓到，"
                               "页面里只有 RSS 源的内容。双击 update-cookie.cmd 扫一次码即可恢复。")

    # 各源最近更新时间（谁停更了一眼可见）
    payload["sources"] = store.source_status()
    days = max(1, round(args.hours / 24))
    payload["window"] = f"近 {days} 天" if days >= 2 else ""

    stats = {
        "items": len(fresh),
        "sources": len({it.source for it in fresh}),
        "raw": len(raw),
    }
    index = render.render(payload, ROOT / "web", stats=stats,
                          reports=store.list_reports(),
                          groups=group_by_day(fresh, date))
    store.save_report(date, payload, index.read_text(encoding="utf-8"))

    store.purge_old(args.keep_days)
    print(f"\n完成：{index}")
    print(f"库内统计：{store.stats()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
