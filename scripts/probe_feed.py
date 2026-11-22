#!/usr/bin/env python
"""探测任意 feed 地址能不能用。

用法：
    python scripts/probe_feed.py https://blocksandfiles.com/feed/ https://example.com/atom.xml
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from ssdintel import fetch  # noqa: E402
from ssdintel.feedparse import parse_feed  # noqa: E402


def main() -> int:
    urls = sys.argv[1:]
    if not urls:
        print(__doc__)
        return 2

    session = fetch.new_session()
    for url in urls:
        try:
            r = session.get(url, timeout=20, allow_redirects=True)
            entries, version = parse_feed(r.content)
            head = f"HTTP {r.status_code}  {version}  {len(entries)} 条  {len(r.content)}B"
            print(f"{head:<52} {url}")
            for e in entries[:2]:
                print(f"    · {e['title'][:70]}")
        except Exception as e:  # noqa: BLE001
            print(f"{'FAIL ' + type(e).__name__:<52} {url}  {str(e)[:90]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
