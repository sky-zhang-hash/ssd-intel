"""数据模型与 SQLite 存储。"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _norm_title(t: str) -> str:
    """归一化标题：去掉空白与标点，用于跨源去重。"""
    t = re.sub(r"\s+", "", t or "")
    t = re.sub(r"[^\w\u4e00-\u9fff]", "", t)
    return t


@dataclass
class Item:
    source: str
    source_type: str            # rss | wechat | manual
    title: str
    url: str
    published: str = ""
    summary: str = ""
    lang: str = "zh"
    weight: float = 0.5
    score: float = 0.0
    categories: list[str] = field(default_factory=list)
    need_resolve: bool = False  # 搜狗跳转链接，需要还原成 mp.weixin 真链

    @property
    def uid(self) -> str:
        return hashlib.sha1(self.url.encode("utf-8")).hexdigest()[:16]

    @property
    def title_key(self) -> str:
        return hashlib.sha1(_norm_title(self.title).encode("utf-8")).hexdigest()[:16]

    def to_row(self) -> tuple:
        return (
            self.uid, self.title_key, self.source, self.source_type, self.title,
            self.url, self.published, self.summary, self.lang, self.weight,
            self.score, json.dumps(self.categories, ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )


DDL = """
CREATE TABLE IF NOT EXISTS items (
    uid         TEXT PRIMARY KEY,
    title_key   TEXT,
    source      TEXT,
    source_type TEXT,
    title       TEXT,
    url         TEXT,
    published   TEXT,
    summary     TEXT,
    lang        TEXT,
    weight      REAL DEFAULT 0,
    score       REAL DEFAULT 0,
    categories  TEXT,
    fetched_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_pub ON items(published);
CREATE INDEX IF NOT EXISTS idx_items_tk  ON items(title_key);
CREATE INDEX IF NOT EXISTS idx_items_fat ON items(fetched_at);

CREATE TABLE IF NOT EXISTS health (
    ts      TEXT,
    name    TEXT,
    ok      INTEGER,
    count   INTEGER,
    detail  TEXT
);

CREATE TABLE IF NOT EXISTS reports (
    date  TEXT PRIMARY KEY,
    json  TEXT,
    html  TEXT
);
"""


class Store:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.executescript(DDL)
        self.conn.commit()

    # ---------- items ----------
    def upsert_items(self, items: list[Item]) -> int:
        """按 uid 去重写入，返回新增条数。"""
        cur = self.conn.cursor()
        added = 0
        for it in items:
            try:
                cur.execute(
                    "INSERT OR IGNORE INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    it.to_row(),
                )
                added += cur.rowcount
            except sqlite3.Error as e:  # 单条失败不影响整批
                print(f"  [warn] 入库失败 {it.title[:30]}...: {e}")
        self.conn.commit()
        return added

    def blank_bad_wechat_urls(self) -> int:
        """把 `originalId` 拼出来的坏链（/s/WR1...）清空，幂等。

        微信读书的 `mpInfo.originalId` 不是真 token，拼出来的链打开是「参数错误」；
        真正的 token 在 `reviewId` 末段（见 `weread._token_from_review`）。
        清空后条目仍然展示，只是没有 ↗ 链接，等 Cookie 有效时抓取会补上真链。
        """
        cur = self.conn.execute(
            "UPDATE items SET url = '' WHERE url LIKE '%mp.weixin.qq.com/s/WR%'")
        self.conn.commit()
        return cur.rowcount

    def drop_blank_urls(self) -> int:
        """清掉占位行（原文链接拿不到时先留内容、URL 置空）。

        下次成功抓到公众号文章后，这些行会被带真链的新行替代。
        """
        cur = self.conn.execute("DELETE FROM items WHERE COALESCE(url,'') = ''")
        self.conn.commit()
        return cur.rowcount

    def has_title_key(self, key: str) -> bool:
        cur = self.conn.execute("SELECT 1 FROM items WHERE title_key = ? LIMIT 1", (key,))
        return cur.fetchone() is not None

    def recent(self, hours: int = 36, min_score: float = 0.0) -> list[Item]:
        cur = self.conn.execute(
            """SELECT source, source_type, title, url, published, summary, lang,
                      weight, score, categories
               FROM items
               WHERE datetime(fetched_at) >= datetime('now', ?)
                 AND score >= ?
               ORDER BY score DESC, published DESC""",
            (f"-{hours} hours", min_score),
        )
        out = []
        for row in cur.fetchall():
            out.append(Item(
                source=row[0], source_type=row[1], title=row[2], url=row[3],
                published=row[4], summary=row[5], lang=row[6], weight=row[7],
                score=row[8], categories=json.loads(row[9] or "[]"),
            ))
        return out

    def purge_old(self, days: int = 60) -> int:
        cur = self.conn.execute(
            "DELETE FROM items WHERE datetime(fetched_at) < datetime('now', ?)",
            (f"-{days} days",),
        )
        self.conn.commit()
        return cur.rowcount

    # ---------- health ----------
    def log_health(self, records: list[dict]) -> None:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.conn.executemany(
            "INSERT INTO health VALUES (?,?,?,?,?)",
            [(ts, r["name"], 1 if r.get("ok") else 0, r.get("count", 0),
              str(r.get("detail") or r.get("error") or "")) for r in records],
        )
        self.conn.commit()

    def last_health(self) -> list[tuple]:
        cur = self.conn.execute(
            """SELECT name, ok, count, detail FROM health
               WHERE ts = (SELECT MAX(ts) FROM health) ORDER BY ok, name"""
        )
        return cur.fetchall()

    # ---------- reports ----------
    def save_report(self, date: str, payload: dict, html: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO reports VALUES (?,?,?)",
            (date, json.dumps(payload, ensure_ascii=False), html),
        )
        self.conn.commit()

    def list_reports(self, limit: int = 120) -> list[dict]:
        """归档页用：最近几期的日期 + 标题（标题存在 payload 里）。"""
        rows = self.conn.execute(
            "SELECT date, json FROM reports ORDER BY date DESC LIMIT ?", (limit,)
        ).fetchall()
        out = []
        for date, payload in rows:
            try:
                data = json.loads(payload or "{}")
            except ValueError:
                data = {}
            out.append({
                "date": date,
                "headline": (data.get("headline") or "").strip(),
            })
        return out

    def stats(self) -> dict:
        c = self.conn.execute
        return {
            "items": c("SELECT COUNT(*) FROM items").fetchone()[0],
            "sources": c("SELECT COUNT(DISTINCT source) FROM items").fetchone()[0],
            "reports": c("SELECT COUNT(*) FROM reports").fetchone()[0],
        }
