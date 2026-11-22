"""轻量 RSS / Atom 解析器（lxml 实现，不引入 feedparser）。

支持：RSS 2.0、RSS 1.0(RDF)、Atom。解析失败一律返回空列表，不抛异常。
"""
from __future__ import annotations

from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

from lxml import etree

ATOM = "http://www.w3.org/2005/Atom"


def _local(el) -> str:
    return etree.QName(el).localname.lower() if isinstance(el.tag, str) else ""


def _text(el) -> str:
    if el is None:
        return ""
    return "".join(el.itertext()).strip()


def _find(el, *names):
    for child in el:
        if _local(child) in names:
            return child
    return None


def _parse_date(raw: str) -> str:
    """把各种日期格式统一成 ISO8601；失败返回空串。"""
    if not raw:
        return ""
    raw = raw.strip()
    # RFC 822（RSS 最常见）：Sat, 22 Nov 2026 10:00:00 +0800
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, IndexError):
        pass
    # ISO 8601（Atom 最常见）
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
        except ValueError:
            continue
    return ""


def _entry(entry) -> dict:
    title = _text(_find(entry, "title"))

    link = ""
    for child in entry:
        if _local(child) == "link":
            link = child.get("href") or _text(child)
            if link:
                break

    summary = _text(_find(entry, "description", "summary"))
    if not summary:
        summary = _text(_find(entry, "encoded", "content"))

    published = _parse_date(
        _text(_find(entry, "pubdate", "published", "updated", "date", "issued"))
    )

    return {"title": title, "link": link.strip(), "summary": summary,
            "published": published}


def parse_feed(data: bytes) -> tuple[list[dict], str]:
    """返回 (entries, 版本描述)。"""
    if not data:
        return [], "empty"
    try:
        parser = etree.XMLParser(recover=True, huge_tree=True, resolve_entities=False)
        root = etree.fromstring(data, parser=parser)
    except etree.XMLSyntaxError:
        return [], "xml-error"
    if root is None:
        return [], "unparsed"

    tag = _local(root)

    if tag == "feed":  # Atom
        entries = [_entry(e) for e in root if _local(e) == "entry"]
        version = "atom"

    elif tag == "rss":  # RSS 2.0
        channel = _find(root, "channel")
        if channel is None:
            return [], "rss-noc"
        entries = [_entry(e) for e in channel if _local(e) == "item"]
        version = "rss" + (root.get("version") or "")

    elif tag == "rdf":  # RSS 1.0
        entries = [_entry(e) for e in root
                   if _local(e) == "item" and e.tag.startswith("{")]
        version = "rdf"

    else:  # 不是 feed，可能被重定向到 HTML 或被墙
        return [], f"not-feed({tag[:12]})"

    entries = [e for e in entries if e["title"] and e["link"]]
    return entries, version
