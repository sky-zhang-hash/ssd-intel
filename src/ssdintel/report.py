"""日报生成：LLM 摘要（DeepSeek）+ 无 LLM 降级摘要。

防幻觉的两个硬约束：
  1. 条目以 [编号] 喂给模型，模型只能引用编号，不能自己写 URL；
  2. 编号 -> URL 的映射在本地完成，模型编不出链接。
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone

import requests

from .models import Item
from . import score as scoring

# 读者在国内，统一按北京时间显示；中国没有夏令时，固定 +8 比 zoneinfo 更稳
# （Windows 上未必装了 tzdata，zoneinfo 会抛 ZoneInfoNotFoundError）。
CST = timezone(timedelta(hours=8))


def local_time(iso: str | None, today: str) -> str:
    """把采集时存的 UTC ISO 时间转成「今天 15:04 / 昨天 09:12 / 11-20 18:30」。"""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    loc = dt.astimezone(CST)
    hm = loc.strftime("%H:%M")
    day = loc.strftime("%Y-%m-%d")
    if day == today:
        return f"今天 {hm}"
    try:
        yest = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    except ValueError:
        yest = ""
    if yest and day == yest:
        return f"昨天 {hm}"
    return f"{loc.strftime('%m-%d')} {hm}"

API_BASE = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
API_URL = f"{API_BASE}/chat/completions"
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

SYSTEM_PROMPT = """你是资深 SSD / 存储行业分析师，为一位关注「产品与技术」的读者写每日情报。
读者的偏好，必须严格遵守：
1. 侧重产品：主控、NAND 颗粒、封装与制造、新品型号与规格、供应链导入。
2. 侧重 AI 对 SSD 的影响：需求侧传导、企业级 eSSD、HBM 挤占 DRAM、AI PC、KV Cache 外溢。
3. 弱化价格：价格只作为一句背景，不要单独成节，不要展开分析涨跌。
4. 只写有信息增量的事，不要复述常识，不要写「随着…的发展」这类空话。

写作红线（违反就是废稿）：
- 正文、标题、watch 里**绝对不要出现「素材」「编号」「第 N 条」这类内部引用**。读者看不到编号，只有你手里有。直接说事情本身。
- **同一件事被多家报道时合并成一条**，ref 填信息最全的那条，text 里可写「多家报道」；不要把同一件事拆成两三条分别复述。
- 每节 3-5 条，全篇不超过 20 条。宁可不写，不要拿低价值素材凑数。
- 素材可能覆盖最近几天（最多一周）：写每条事情的**最新进展**，不要按日期写流水账，也不要因为两天前报道过就整条丢掉；同一事件的早期报道与后续进展合成一条。
- text 60-90 字，先事实、后影响，不要写"综上所述"。

输出必须是 JSON，结构：
{
  "headline": "一句话点出今天最重要的一件事（不超过 40 字）",
  "sections": [
    {"title": "板块名", "points": [
        {"ref": 素材编号整数, "text": "这条的事实 + 对产品的影响，60-90 字", "impact": "可选：对产品/供应链的具体影响"}
    ]}
  ],
  "watch": ["值得关注但尚未证实的信号，1-3 条，没有就空数组；同样不要提编号"],
  "price_note": "价格背景一句话，没有就空字符串"
}

板块名从这几个里选，没有内容的板块不要输出：
主控与新品 / 颗粒与工艺 / 封装与制造 / AI × SSD / 供应链动向
"""


def _material_list(items: list[Item], limit: int = 120) -> str:
    rows = []
    for i, it in enumerate(items[:limit], 1):
        summ = re.sub(r"\s+", " ", it.summary or "")[:180]
        cats = ",".join(it.categories) or "其他"
        rows.append(f"[{i}] ({it.source} | {cats}) {it.title} —— {summ}")
    return "\n".join(rows)


def _post(url: str, headers: dict, body: dict, timeout: int):
    return requests.post(url, headers=headers, json=body, timeout=timeout)


def llm_report(items: list[Item], date: str, api_key: str | None = None,
               model: str | None = None, timeout: int = 180) -> dict | None:
    api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return None
    if not items:
        return None

    materials = _material_list(items)
    user = f"日期：{date}\n\n今日素材：\n{materials}\n\n请按系统提示输出 JSON。"

    body = {
        "model": model or MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
        "max_tokens": 4000,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        r = _post(API_URL, headers, body, timeout)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
    except requests.HTTPError as e:
        print(f"  [llm] HTTP 错误：{e} | {getattr(e.response, 'text', '')[:200]}")
        return None
    except (KeyError, ValueError) as e:
        print(f"  [llm] 解析失败：{e}")
        return None

    # 把 ref 映射回真实条目，模型输出里不带 URL
    def resolve(ref) -> Item | None:
        try:
            idx = int(ref) - 1
        except (TypeError, ValueError):
            return None
        return items[idx] if 0 <= idx < len(items) else None

    def clean(text) -> str:
        """兜底：模型偶尔还是会写「素材6/第3条」，读者看不到编号，去掉。"""
        s = str(text or "").strip()
        s = re.sub(r"素材\s*\d+\s*(所称|提到|所述|中|的)?", "", s)
        s = re.sub(r"第\s*\d+\s*条", "", s)
        s = re.sub(r"[（(]\s*编号\s*\d+\s*[)）]", "", s)
        s = re.sub(r"\s{2,}", " ", s)
        return s.strip(" ，,；;")

    sections = []
    for sec in data.get("sections") or []:
        points = []
        for p in sec.get("points") or []:
            src = resolve(p.get("ref"))
            if not src:
                continue
            points.append({
                "text": clean(p.get("text")),
                "impact": clean(p.get("impact")),
                "source": src.source,
                "url": src.url,
                "time": local_time(src.published, date),
                "cats": src.categories,
            })
        if points:
            sections.append({"title": sec.get("title", "动态"), "points": points})

    if not sections:
        print("  [llm] 返回内容为空，回退到降级摘要")
        return None

    return {
        "date": date,
        "headline": clean(data.get("headline")),
        "sections": sections,
        "watch": [clean(w) for w in (data.get("watch") or []) if clean(w)],
        "price_note": clean(data.get("price_note")),
        "mode": "llm",
    }


SECTION_TITLES = {
    "主控": "主控与新品",
    "颗粒": "颗粒与工艺",
    "封装": "封装与制造",
    "AI": "AI × SSD",
    "产品": "产品与新品",
    "供应链": "供应链动向",
}


def digest_report(items: list[Item], date: str, per_section: int = 6) -> dict:
    """无 LLM 降级：按类别分组，只出标题 + 链接。保证永远有输出。"""
    grouped = scoring.group(items)
    sections = []
    for label, group_items in grouped.items():
        if label == "价格":
            continue
        points = [
            {"text": it.title, "impact": "", "source": it.source,
             "url": it.url, "time": local_time(it.published, date),
             "cats": it.categories}
            for it in group_items[:per_section]
        ]
        if points:
            sections.append({"title": SECTION_TITLES.get(label, label), "points": points})

    price_items = [it for it in items if "价格" in it.categories]
    # 价格只做一句背景：挑一条没被任何板块收进去的，避免同一句话出现两遍。
    shown = {p["url"] for s in sections for p in s["points"]}
    price_note = ""
    for it in price_items:
        if it.url not in shown:
            price_note = it.title
            break

    return {
        "date": date,
        "headline": sections[0]["points"][0]["text"] if sections else "今日无重要动态",
        "sections": sections,
        "watch": [],
        "price_note": price_note,
        "mode": "digest",
    }


def build(items: list[Item], date: str | None = None, api_key: str | None = None) -> dict:
    date = date or datetime.now().strftime("%Y-%m-%d")
    report = llm_report(items, date, api_key=api_key)
    if report is None:
        print("  [report] 使用降级摘要（未配置 DEEPSEEK_API_KEY 或调用失败）")
        report = digest_report(items, date)
    return report
