"""采集层：RSS 通用源 + 搜狗微信关键词发现。

设计原则：单个源失败绝不影响整批。所有异常都收敛成 health 记录。
"""
from __future__ import annotations

import random
import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from .feedparse import parse_feed
from .models import Item

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

SOGOU_HOME = "https://weixin.sogou.com"
SOGOU_SEARCH = SOGOU_HOME + "/weixin"


def new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    return s


def _strip_html(html: str | None, limit: int = 800) -> str:
    if not html:
        return ""
    txt = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = re.sub(r"&[a-zA-Z#0-9]+;", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()[:limit]


def _published(entry) -> str:
    """兼容旧接口；feedparse 已统一处理日期，这里保留给手动补录用。"""
    return entry.get("published") or ""


# --------------------------------------------------------------------------
# RSS
# --------------------------------------------------------------------------
def fetch_rss(sources: list[dict], session: requests.Session | None = None,
              per_source: int = 40, timeout: int = 25):
    """抓取全部 RSS 源。返回 (items, health)。"""
    session = session or new_session()
    items: list[Item] = []
    health: list[dict] = []

    for src in sources:
        if not src.get("enabled", True):
            health.append({"name": src["name"], "ok": True, "count": 0, "detail": "skipped"})
            continue
        name = src["name"]
        try:
            resp = session.get(src["url"], timeout=timeout, allow_redirects=True)
            resp.raise_for_status()
            entries, version = parse_feed(resp.content)
            got = 0
            for e in entries[:per_source]:
                title = _strip_html(e["title"], 300)
                link = (e["link"] or "").strip()
                if not title or not link:
                    continue
                items.append(Item(
                    source=name,
                    source_type="rss",
                    title=title,
                    url=link,
                    published=e["published"],
                    summary=_strip_html(e["summary"]),
                    lang=src.get("lang", "zh"),
                    weight=float(src.get("weight", 0.5)),
                ))
                got += 1
            health.append({"name": name, "ok": bool(got), "count": got, "detail": version})
            print(f"  [rss] {name:<24} {got:>3} 条  {version}")
        except Exception as e:  # noqa: BLE001 - 采集层必须吞掉所有异常
            msg = f"{type(e).__name__}: {e}"[:160]
            health.append({"name": name, "ok": False, "count": 0, "error": msg})
            print(f"  [rss] {name:<24} 失败  {msg}")
        time.sleep(0.5)

    return items, health


# --------------------------------------------------------------------------
# 搜狗微信
# --------------------------------------------------------------------------
def _looks_blocked(html: str) -> bool:
    return ("请输入验证码" in html) or ("antispider" in html) or ("访问过于频繁" in html)


def _resolve_once(path: str, session: requests.Session,
                  timeout: int = 20) -> tuple[str, bool]:
    """还原一条搜狗跳转链。返回 (真链, 是否被反爬)。

    搜狗在返回页里用 JS 拼接 url += '...' 的方式藏真链，
    把片段拼起来即可，不需要浏览器。
    """
    try:
        r = session.get(SOGOU_HOME + path, timeout=timeout)
        if _looks_blocked(r.text):
            return "", True
        parts = re.findall(r"url\s*\+=\s*'([^']*)'", r.text)
        if parts:
            return "".join(parts).replace("@", ""), False
        return "", False
    except requests.RequestException:
        return "", False


def resolve_sogou_link(href: str, session: requests.Session, timeout: int = 20) -> str:
    if not href.startswith("/link"):
        return href if href.startswith("http") else ""
    return _resolve_once(href, session, timeout)[0]


def search_wechat(query: str, session: requests.Session | None = None,
                  page: int = 1, timeout: int = 20, resolve: bool = False):
    """按关键词搜公众号文章。返回 (items, health)。"""
    session = session or new_session()
    params = {"type": "2", "query": query, "page": page, "ie": "utf8", "s_from": "input"}
    try:
        r = session.get(SOGOU_SEARCH, params=params, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException as e:
        return [], {"name": f"sogou:{query}", "ok": False, "error": f"{type(e).__name__}: {e}"}

    if _looks_blocked(r.text):
        return [], {"name": f"sogou:{query}", "ok": False, "error": "被反爬拦截（验证码/频率）"}

    soup = BeautifulSoup(r.text, "lxml")
    items: list[Item] = []
    # 结果块 id：sogou_vr_11002601_box_0/1/2...，只认这些，别把侧栏推荐也算进来
    for li in soup.select('li[id^="sogou_vr_11002601_box_"]'):
        a = li.select_one("h3 a")
        if not a:
            continue
        title = a.get_text(" ", strip=True)
        href = a.get("href", "")
        if not title or not href:
            continue

        # 公众号名在 all-time-y2，不在 .account（后者是旧版结构）
        acc_el = li.select_one("span.all-time-y2") or li.select_one(".account")
        account = acc_el.get_text(" ", strip=True) if acc_el else ""

        # 发布时间：页面里是 document.write(timeConvert('1699999999')) 这样的脚本
        ts_m = re.search(r"timeConvert\('(\d{9,11})'\)", str(li))
        published = ""
        if ts_m:
            try:
                published = datetime.fromtimestamp(
                    int(ts_m.group(1)), tz=timezone.utc
                ).isoformat(timespec="seconds")
            except (ValueError, OSError, OverflowError):
                published = ""

        snippet_el = li.select_one(".txt-info")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""

        url = resolve_sogou_link(href, session) if resolve else ""
        is_sogou_jump = not url
        items.append(Item(
            source=account or "微信公众号",
            source_type="wechat",
            title=title,
            url=url or (SOGOU_HOME + href),
            published=published,
            summary=snippet,
            lang="zh",
            weight=0.75,
            need_resolve=is_sogou_jump,
        ))
    return items, {"name": f"sogou:{query}", "ok": bool(items), "count": len(items),
                   "detail": f"page {page}"}


def collect_wechat(queries: list[str], session: requests.Session | None = None,
                   pages: int = 1, resolve: bool = False, delay: float = 8.0):
    """L1 策略：关键词轮询。

    delay 是基准间隔，实际用 [0.75×, 1.6×] 随机抖动 —— 固定间隔更容易被判定为爬虫。
    """
    session = session or new_session()
    all_items: list[Item] = []
    health: list[dict] = []
    for q in queries:
        for p in range(1, pages + 1):
            items, h = search_wechat(q, session=session, page=p, resolve=resolve)
            all_items.extend(items)
            health.append(h)
            print(f"  [wx]  {q:<20} p{p}  {len(items):>2} 条")
            if not h.get("ok") and "反爬" in str(h.get("error", "")):
                print("  [wx]  触发反爬，停止本轮公众号采集")
                return all_items, health
            time.sleep(random.uniform(delay * 0.75, delay * 1.6))
    return all_items, health


def resolve_items(items: list[Item], session: requests.Session | None = None,
                  limit: int = 6, delay: float = 10.0) -> list[Item]:
    """把搜狗跳转链还原成 mp.weixin 真链。

    实测：搜狗对 /link 有独立的 IP 级反爬，连着请求十几条就开始返回
    「请输入验证码」，而且会持续一段时间。所以这里刻意做得很克制：
      · 只还原分数最高的几条（最可能上日报的）
      · 每条之间停 10 秒左右
      · 一遇到反爬立刻停手，剩下的保留搜狗链
    搜狗链在浏览器里通常也能跳转，只是难看一下，不影响使用。
    """
    todo = sorted(
        (it for it in items if it.need_resolve),
        key=lambda x: x.score, reverse=True,
    )[:limit]
    if not todo:
        return items

    session = session or new_session()
    done = 0
    for it in todo:
        path = it.url[len(SOGOU_HOME):] if it.url.startswith(SOGOU_HOME) else ""
        if not path.startswith("/link"):
            it.need_resolve = False
            continue
        real, blocked = _resolve_once(path, session)
        if blocked:
            print(f"  [wx]  搜狗反爬，停止还原（已还原 {done} 条）")
            break
        if real:
            it.url = real
            it.need_resolve = False
            done += 1
        time.sleep(random.uniform(delay * 0.7, delay * 1.4))
    if done:
        print(f"  [wx]  还原真链 {done}/{len(todo)}")
    return items

