"""微信公众号采集（L2）：走微信读书的公众号接口。

为什么不用搜狗：搜狗按相关度排序、时间过滤参数失效，实测 95.6% 是 30 天前的旧文，
当不了每日新闻源（见 README「试过但不可行的路径」）。

微信读书这边是另一回事——它把公众号当"书"来订阅，有正规的列表接口，
返回的是**按时间倒序**的文章流，带标题、摘要、发布时间、阅读数，正是我们要的。
它不提供正文 HTML，但我们的采集只用到标题+摘要+链接，够用。

接口（逆向自 WeRSS 项目，已实测）：
    GET /web/search/global?keyword=闪存市场&maxIdx=0&count=20
        → payload["mp"] 里是公众号，bookId 形如 MP_WXS_3xxxxxxxxx
          （匿名调用只有 books 段，必须带登录 Cookie）
    GET /web/mp/articles?bookId=MP_WXS_xxx&offset=0
        → payload["reviews"][].subReviews[].review.mpInfo
          字段：title / originalId / content(摘要) / time / readNum / likeNum

Cookie 从浏览器登录 weread.qq.com 后复制，整串丢进 .env 的 WEREAD_COOKIE 即可。
"""
from __future__ import annotations

import random
import re
import time
from datetime import datetime, timedelta, timezone

import requests

from .models import Item

BASE = "https://weread.qq.com"

# 微信读书会校验 UA；普通 requests 的默认 UA 会被拦
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 这些错误码是账号级问题（Cookie 失效 / 参数不对），再重试也没意义
FATAL_CODES = {-2010, -2012}

# -2014「请求过于频繁」不是账号问题，是限流：等一会儿重试即可。
# （一度把它当致命错误，结果一轮只拿到 500 多篇就整个停了；实测等 20-40 秒就能恢复）
RATE_LIMIT_CODES = {-2014, -2041}  # -2041 也是频控（实测：短时间连打即触发，几分钟到几十分钟自解）


class WereadError(Exception):
    def __init__(self, code, message, retriable: bool = True, rate_limit: bool = False):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.retriable = retriable
        self.rate_limit = rate_limit


def new_session(cookie: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Cookie": cookie,
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Origin": BASE,
        "Referer": BASE + "/",
    })
    return s


def _check(payload: dict) -> None:
    """接口用 200 + errcode 表示失败，不能只看 HTTP 状态码。"""
    if not isinstance(payload, dict):
        raise WereadError("bad_payload", "返回不是 JSON 对象")
    code = payload.get("errcode", payload.get("errCode", 0)) or 0
    if not code:
        return
    msg = payload.get("errmsg") or payload.get("errMsg") or ""
    if code in FATAL_CODES:
        hint = "Cookie 失效或配额用完，重新复制一次 Cookie"
        raise WereadError(code, f"{msg or '账号级错误'}（{hint}）", retriable=False)
    if code in RATE_LIMIT_CODES:
        raise WereadError(code, msg or "请求过于频繁", rate_limit=True)
    raise WereadError(code, msg or "未知错误")


def _get(session: requests.Session, path: str, params: dict, timeout: int = 25,
         retries: int = 3) -> dict:
    """发请求；网络抖动重试，但配额类限流（-2014/-2041）立刻上抛。

    实测 -2041 是账号级频控，冷却要几分钟到几小时，短退避重试没意义，
    反而把额度烧得更狠；由 collect() 决定这一轮直接收工。
    """
    for attempt in range(retries):
        try:
            return _get_once(session, path, params, timeout)
        except WereadError as e:
            if e.rate_limit or not e.retriable or attempt == retries - 1:
                raise
            wait = 3 * (2 ** attempt)  # 3s / 6s / 12s，只给真正的网络抖动
            print(f"  [wx]  请求失败（{e.code}），{wait}s 后重试")
            time.sleep(wait)
    raise WereadError("unreachable", "重试耗尽")


def _get_once(session: requests.Session, path: str, params: dict, timeout: int = 25) -> dict:
    try:
        r = session.get(BASE + path, params=params, timeout=timeout)
    except requests.RequestException as e:
        raise WereadError("network", f"{type(e).__name__}: {e}") from e
    if r.status_code == 499:  # 微信读书用 499 表示「太频繁 / 配额用尽」
        raise WereadError(499, "请求过于频繁（HTTP 499）", rate_limit=True)
    if r.status_code != 200:
        raise WereadError(r.status_code, f"HTTP {r.status_code}")
    try:
        payload = r.json()
    except ValueError as e:
        raise WereadError("invalid_json", "返回不是 JSON") from e
    _check(payload)
    return payload


# --------------------------------------------------------------------------
# 公众号搜索：名字 → bookId
# --------------------------------------------------------------------------
def search_mp(session: requests.Session, keyword: str, count: int = 20) -> list[dict]:
    """搜公众号。返回 [{"book_id", "title", "author"}]，只保留 MP_WXS_ 形态的。"""
    payload = _get(session, "/web/search/global",
                   {"keyword": keyword, "maxIdx": 0, "count": count})
    out = []
    for sec in ("mp", "books"):  # 两个段都扫，避免接口改版后漏
        for it in payload.get(sec) or []:
            info = it.get("bookInfo") or it
            bid = str(info.get("bookId") or "")
            if not bid.startswith("MP_WXS"):
                continue
            out.append({
                "book_id": bid,
                "title": (info.get("title") or info.get("name") or "").strip(),
                "author": (info.get("author") or "").strip(),
            })
    return out


def resolve_account(session: requests.Session, name: str) -> dict | None:
    """按公众号名找到 bookId。优先精确同名，其次取第一个结果。"""
    try:
        hits = search_mp(session, name)
    except WereadError as e:
        if not e.retriable:
            raise
        return None
    for h in hits:
        if h["title"] == name:
            return h
    return hits[0] if hits else None


# --------------------------------------------------------------------------
# 文章列表
# --------------------------------------------------------------------------
def _fix_token(token: str) -> str:
    """微信读书把文章 token 里的 _ 写成了 ~，换回来才是真链。

    不换的话 mp.weixin.qq.com 会报"参数错误"（WeRSS 的注释称实测 149 篇全部命中）。
    """
    return (token or "").replace("~", "_")


def _token_from_review(review_id: str, book_id: str = "") -> str:
    """从 reviewId 里取真正的文章 token。

    reviewId 形如 ``MP_WXS_3095382082_CgTzcUPf0E9NlYhdBqVLiw``，末段才是
    mp.weixin.qq.com 的短链 token；``mpInfo.originalId`` 是微信读书自己包了一层
    （``WR1`` 开头、76 位），拿它拼出来的链**一律「参数错误」**——2026-11-22 实测。
    """
    rid = (review_id or "").strip()
    if not rid:
        return ""
    prefix = f"{book_id}_" if book_id else ""
    if prefix and rid.startswith(prefix):
        rid = rid[len(prefix):]
    elif "_" in rid:
        rid = rid.split("_")[-1]
    # 拆分依赖原始的 '_'，~ → _ 的还原必须放在拆分之后
    return _fix_token(rid)


def parse_articles(payload: dict) -> list[dict]:
    out: list[dict] = []
    for group in payload.get("reviews") or []:
        group_time = group.get("createTime") or 0
        for sub in group.get("subReviews") or []:
            review = sub.get("review") or {}
            info = review.get("mpInfo") or {}
            title = (info.get("title") or "").strip()
            # 只用 reviewId 里的 token；originalId（WR1 开头 76 位）拼出来是死链，不用
            token = _token_from_review(review.get("reviewId") or "")
            # 防御：万一某天 reviewId 里塞的还是 WR1 那种包装 id，就别放出去变成死链
            if token.startswith("WR1") or len(token) > 40:
                token = ""
            if not title or not token:
                continue
            out.append({
                "title": title,
                "url": f"https://mp.weixin.qq.com/s/{token}",
                "summary": (info.get("content") or review.get("content") or "").strip(),
                "published": _ts(info.get("time") or review.get("createTime") or group_time),
                "read_num": info.get("readNum") or 0,
                "like_num": info.get("likeNum") or 0,
            })
    return out


def _ts(value) -> str:
    """把秒/毫秒时间戳统一成 UTC ISO，和 feedparse 的输出格式保持一致。"""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    if n > 10**12:  # 毫秒
        n //= 1000
    try:
        return datetime.fromtimestamp(n, tz=timezone.utc).isoformat(timespec="seconds")
    except (ValueError, OSError, OverflowError):
        return ""


def fetch_articles(session: requests.Session, book_id: str, pages: int = 1,
                   delay: float = 2.5) -> list[dict]:
    """翻页拉某个公众号的文章，新→旧。

    注意 offset 的语义：微信读书按**顶层 review group** 计数，不是按文章、也不是页码。
    一页通常返回 1 个 group（里面若干篇），所以要 offset += len(reviews)。
    当成页码 +1 会原地踏步，拿到的永远是同一页。
    """
    got: list[dict] = []
    offset = 0
    for page in range(max(pages, 1)):
        if page:
            time.sleep(random.uniform(delay * 0.8, delay * 1.5))
        payload = _get(session, "/web/mp/articles",
                       {"bookId": book_id, "offset": offset})
        groups = payload.get("reviews") or []
        batch = parse_articles(payload)
        if not batch or not groups:
            break
        got.extend(batch)
        offset += len(groups)
    return got


# --------------------------------------------------------------------------
# 批量采集
# --------------------------------------------------------------------------
def collect(book_ids: dict[str, str], cookie: str, pages: int = 1,
            delay: float = 2.5, limit: int = 0):
    """按 {公众号名: bookId} 批量拉取。

    单个号失败不影响其他号——和 RSS 采集一样的容错要求。
    limit > 0 时只跑前 limit 个号（调试用）。
    """
    session = new_session(cookie)
    items: list[Item] = []
    health: list[dict] = []

    names = list(book_ids.items())
    if limit:
        names = names[:limit]

    for name, book_id in names:
        try:
            arts = fetch_articles(session, book_id, pages=pages, delay=delay)
        except WereadError as e:
            print(f"  [wx]  {name:<16} 失败  {e}")
            health.append({"name": f"weread:{name}", "ok": False, "error": str(e)[:160]})
            if not e.retriable:  # Cookie 失效，后面的号也拿不到，直接停
                print("  [wx]  Cookie 有问题，停止本轮公众号采集")
                break
            if e.rate_limit:  # 退避重试也没救回来，继续跑只会越撞越久
                print("  [wx]  限流未缓解，本轮先收工（已采到的照常入库）")
                break
            continue

        for a in arts:
            items.append(Item(
                source=name,
                source_type="wechat",
                title=a["title"],
                url=a["url"],
                published=a["published"],
                summary=a["summary"],
                lang="zh",
                weight=0.75,
            ))
        health.append({"name": f"weread:{name}", "ok": bool(arts), "count": len(arts)})
        print(f"  [wx]  {name:<16} {len(arts):>2} 篇")
        time.sleep(random.uniform(delay * 0.8, delay * 1.5))

    return items, health

def cover_link(session: requests.Session, book_id: str) -> tuple[str, str]:
    """每个号最新一篇：(标题, 原文链接)。

    `/api/mp/cover` 不校验登录态，文章列表被限流时它还能用——所以留作兜底：
    至少能把每号最新一篇的链接补上。
    """
    payload = _get(session, "/api/mp/cover", {"bookId": book_id}, timeout=20, retries=1)
    title = str(payload.get("title") or "").strip()
    token = _token_from_review(str(payload.get("reviewId") or ""), book_id)
    if token.startswith("WR1") or len(token) > 40:
        token = ""
    return title, (f"https://mp.weixin.qq.com/s/{token}" if token else "")


def cover_links(book_ids: dict[str, str], cookie: str, delay: float = 1.2) -> dict[str, str]:
    """{归一化标题: 原文链接}，给 `Store.fill_missing_urls` 用。"""
    from .models import _norm_title  # 局部导入，避免循环

    session = new_session(cookie)
    out: dict[str, str] = {}
    for name, book_id in book_ids.items():
        try:
            title, url = cover_link(session, book_id)
        except WereadError as e:
            print(f"  [wx]  cover {name} 失败 {e}")
            continue
        if title and url:
            out[_norm_title(title)] = url
        time.sleep(delay)
    return out

_CTA_RE = re.compile(r'var\s+ct\s*=\s*"(\d{10})"')
_PUB_RE = re.compile(r'id="publish_time"[^>]*>([^<]{6,40})<')
_BODY_RE = re.compile(r'id="js_content".*?>(.*?)</div>', re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def article_text(session: requests.Session, review_id: str, timeout: int = 30) -> tuple[str, str]:
    """一篇文章的 (正文纯文本, 发布时间 UTC ISO)。

    用 `/web/mp/content?reviewId=`（不在被限流的 `/web/mp/articles` 上）：
    实测能拿到整页 HTML，正文在 `#js_content`，时间在 `var ct` 或 `#publish_time`。
    """
    if not review_id:
        return "", ""
    try:
        r = session.get(BASE + "/web/mp/content", params={"reviewId": review_id}, timeout=timeout)
    except requests.RequestException as e:
        print(f"  [wx]  正文拉取失败：{e}")
        return "", ""
    if r.status_code != 200:
        return "", ""
    html = r.text
    published = ""
    ts = _CTA_RE.search(html)
    if ts:
        published = _ts(int(ts.group(1)))
    else:
        pub = _PUB_RE.search(html)
        if pub:
            published = _ts(_ts_from_text(pub.group(1)))
    body = ""
    m = _BODY_RE.search(html)
    if m:
        body = _TAG_RE.sub("", m.group(1))
        body = re.sub(r"&nbsp;", " ", body)
        body = re.sub(r"\s+", " ", body).strip()
    return body, published


def _ts_from_text(text: str) -> int:
    """把页面上的「2026-11-25 20:00」换成时间戳；认不出来就返回 0。"""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})", text or "")
    if not m:
        return 0
    from datetime import datetime, timezone as _tz
    try:
        dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                      int(m.group(4)), int(m.group(5)), tzinfo=_tz(timedelta(hours=8)))
    except ValueError:
        return 0
    return int(dt.timestamp())


def cover_items(book_ids: dict[str, str], cookie: str = "", delay: float = 1.2) -> list:
    """Cookie 失效时的退路：每个号取最新一篇，直接当今天的公众号条目。

    只有标题和链接（`/api/mp/cover` 不给发布时间和摘要），但总比整个板块空着强；
    下次 Cookie 有效时会用带时间的完整条目替代。
    """
    from .models import Item  # 局部导入，避免循环

    session = new_session(cookie) if cookie else new_session("")
    out = []
    for name, book_id in book_ids.items():
        try:
            payload = _get(session, "/api/mp/cover", {"bookId": book_id}, timeout=20, retries=1)
        except WereadError as e:
            print(f"  [wx]  cover {name} 失败 {e}")
            continue
        title = str(payload.get("title") or "").strip()
        review_id = str(payload.get("reviewId") or "")
        token = _token_from_review(review_id, book_id)
        if token.startswith("WR1") or len(token) > 40:
            token = ""
        if title:
            body, published = article_text(session, review_id)
            out.append(Item(source=name, source_type="wechat", title=title,
                            url=(f"https://mp.weixin.qq.com/s/{token}" if token else ""),
                            summary=body[:1200], published=published, weight=0.68))
            print(f"  [wx]  cover {name}: {title[:24]} 正文 {len(body)} 字")
        time.sleep(delay)
    return out

# --------------------------------------------------------------------------
# keeper 快照（Node fetch 能过 -2041，Python requests 过不了）
# --------------------------------------------------------------------------
def load_snapshot(path, cookie: str = "", max_age_hours: float = 8.0,
                  enrich_top: bool = True, delay: float = 1.2):
    """读 keeper 每轮导出的 data/wechat_latest.json。

    返回 (items, health, meta)。文件不存在或过期时返回 ([], [], {"reason": ...})，
    由调用方决定要不要退回网络采集——绝不静默当成功（规则 11.1）。
    """
    import json
    import os
    from datetime import datetime as _dt, timezone as _tz

    if not os.path.exists(path):
        return [], [], {"reason": "no-file"}
    try:
        with open(path, encoding="utf-8") as f:
            snap = json.load(f)
    except (OSError, ValueError) as e:
        return [], [], {"reason": f"bad-file:{e}"}

    fetched = snap.get("fetched_at") or ""
    age_h = None
    if fetched:
        try:
            ts = _dt.fromisoformat(fetched.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=_tz.utc)
            age_h = (_dt.now(_tz.utc) - ts).total_seconds() / 3600.0
        except ValueError:
            age_h = None
    if age_h is not None and age_h > max_age_hours:
        return [], [], {"reason": "stale", "age_h": round(age_h, 1), "fetched_at": fetched}

    items, health = [], []
    session = new_session(cookie) if (cookie and enrich_top) else None
    for acc in snap.get("accounts") or []:
        name = acc.get("name") or ""
        arts = acc.get("articles") or []
        health.append({"source": name, "count": len(arts)})
        for i, a in enumerate(arts):
            title = (a.get("title") or "").strip()
            url = a.get("url") or ""
            if not title or not url:
                continue
            summary = ""
            published = a.get("published") or ""
            # 只给每个号的最新一篇取正文，其余保留标题（省请求，也避开频控）
            if session is not None and i == 0 and a.get("review_id"):
                try:
                    body, pub = article_text(session, a["review_id"])
                    summary = (body or "")[:1200]
                    published = published or pub
                    print(f"  [wx]  snapshot {name}: {title[:24]} 正文 {len(body or '')} 字")
                except WereadError as e:
                    print(f"  [wx]  snapshot {name} 正文失败 {e.code}（保留标题）")
                time.sleep(random.uniform(delay * 0.8, delay * 1.4))
            items.append(Item(source=name, source_type="wechat", title=title,
                              url=url, published=published, summary=summary,
                              weight=0.66))
    meta = {"reason": "ok", "fetched_at": fetched, "age_h": round(age_h, 1) if age_h else None,
            "accounts": len(snap.get("accounts") or [])}
    return items, health, meta
