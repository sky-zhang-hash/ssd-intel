#!/usr/bin/env python
"""检查 config/sources.yaml 里每个源是否还活着。

用法：
    python scripts/verify_sources.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import yaml  # noqa: E402

from ssdintel import fetch  # noqa: E402


def main() -> int:
    with open(ROOT / "config" / "sources.yaml", encoding="utf-8") as f:
        sources = yaml.safe_load(f).get("sources", [])

    session = fetch.new_session()
    items, health = fetch.fetch_rss(sources, session=session)

    print("\n" + "=" * 74)
    print(f"{'源':<26}{'状态':<8}{'条数':<6}说明")
    print("=" * 74)
    for h in health:
        state = "OK" if h.get("ok") else "FAIL"
        detail = str(h.get("detail") or h.get("error") or "")[:36]
        print(f"{h['name']:<26}{state:<8}{h.get('count', 0):<6}{detail}")

    ok = sum(1 for h in health if h.get("ok"))
    print("=" * 74)
    print(f"可用 {ok}/{len(health)}，共取到 {len(items)} 条")
    print("失败的源请改 config/sources.yaml 里的 url，或设 enabled: false")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
