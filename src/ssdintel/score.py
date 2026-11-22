"""分类、打分与过滤。

三道闸门，从硬到软：
  1. exclude  —— 命中直接丢（招聘/抽奖这类纯噪音）
  2. anchors  —— 必须命中至少一个存储锚点词，挡掉泛 AI / 泛半导体
  3. core + min_score —— 必须命中核心类别且分数过线

关键词匹配规则：
  · 纯 ASCII 词用词边界匹配，避免 "AI" 命中 "MAIL"、"SSD" 命中 "SSDSpeed"
  · 中文词直接子串匹配
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import yaml

from .models import Item


def load_rules(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        rules = yaml.safe_load(f)
    rules.setdefault("min_score", 0.45)
    rules.setdefault("anchors", [])
    rules.setdefault("exclude", [])
    return rules


def _match(term: str, text: str) -> bool:
    if term.isascii():
        pat = rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])"
        return re.search(pat, text, re.I) is not None
    return term in text


def classify(item: Item, rules: dict) -> Item:
    text = f"{item.title} {item.summary}"
    hits, score = [], 0.0
    for cat in rules["categories"]:
        if any(_match(t, text) for t in cat["terms"]):
            hits.append(cat["name"])
            score += float(cat.get("weight", 0.5))
    item.categories = hits
    item.score = round(score * float(item.weight or 0.5), 3)
    return item


def keep(item: Item, rules: dict) -> bool:
    text = f"{item.title} {item.summary}"

    if any(_match(t, text) for t in rules["exclude"]):
        return False

    # 锚点只匹配标题，不匹配摘要。
    # 踩过的坑：主板评测的摘要里常写一句「支持两个 M.2 SSD 插槽」，
    # 拿摘要匹配会把整篇主板文章放进来。
    anchors = rules["anchors"]
    if anchors and not any(_match(t, item.title) for t in anchors):
        return False

    core = {c["name"] for c in rules["categories"] if c.get("core")}
    if not (set(item.categories) & core):
        return False

    return item.score >= float(rules["min_score"])


def apply(items: list[Item], rules: dict) -> list[Item]:
    scored = [classify(it, rules) for it in items]
    return [it for it in scored if keep(it, rules)]


def filter_fresh(items: list[Item], max_age_days: int) -> list[Item]:
    """丢掉发布时间太旧的条目。

    为什么必须有：搜狗微信只按相关度排序（时间排序参数 tsn=1 实测失效），
    实测结果里 95.6% 是 30 天以上的旧文、只有 1.5% 在 7 天内。
    不按时间过滤，日报里会满是几年前的「主流主控盘点」。
    没有发布时间的条目保留 —— RSS 偶尔缺日期，宁可留也别误杀。
    """
    if max_age_days <= 0:
        return items
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    out = []
    for it in items:
        if not it.published:
            out.append(it)
            continue
        try:
            dt = datetime.fromisoformat(it.published)
        except ValueError:
            out.append(it)
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt >= cutoff:
            out.append(it)
    return out


def dedupe(items: list[Item]) -> list[Item]:
    """同一事件常被多源报道。按归一化标题去重，保留分数更高的那条。"""
    best: dict[str, Item] = {}
    for it in items:
        key = it.title_key
        cur = best.get(key)
        if cur is None or it.score > cur.score:
            best[key] = it
    return list(best.values())


def group(items: list[Item]) -> dict[str, list[Item]]:
    """按第一个命中类别分组，供无 LLM 时的降级摘要使用。"""
    order = ["主控", "颗粒", "封装", "产品", "AI", "供应链", "价格"]
    out: dict[str, list[Item]] = {}
    for it in items:
        label = next((c for c in order if c in it.categories), "其他")
        out.setdefault(label, []).append(it)
    for v in out.values():
        v.sort(key=lambda x: x.score, reverse=True)
    return out
