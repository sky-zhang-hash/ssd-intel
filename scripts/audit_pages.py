"""渲染产物自检：转义、版本标记、入口、缓存注册这四类隐性 bug 的断言。

规则 7.1 / 7.2 / 7.3 / 6.2 都靠这个脚本兜底。跑在 run_daily.py 之后。

用法：
    python scripts/audit_pages.py

退出码：0 = 通过，1 = 有不满足的断言。
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PAGES = ["index.html", "all.html", "archive.html", "fav.html", "install.html"]


def main() -> int:
    fails: list[str] = []
    for name in PAGES:
        p = WEB / name
        if not p.exists():
            fails.append(f"{name}: 文件不存在（先跑 run_daily.py）")
            continue
        html = p.read_text(encoding="utf-8")
        checks = [
            # 7.2 转义：模板里的 HTML 字符串必须 | safe，否则会在正文里印出源码文本
            ("转义", "&lt;nav class=" not in html and "&lt;script" not in html),
            # 6.2 版本标记
            ("built 标记", '<meta name="built" content="' in html),
            # 7.3 等价入口（下拉手势之外必须有可点的刷新按钮）
            ("刷新按钮", "refresh-btn" in html),
            # 7.1 service worker 注册（模板拆分时曾漏掉）
            ("SW 注册", "serviceWorker" in html and "sw.js" in html),
            # 相对路径不能写成根路径（Pages 部署在子目录）
            ("相对路径", 'href="/' not in html and 'src="/' not in html),
        ]
        for label, ok in checks:
            if not ok:
                fails.append(f"{name}: {label} 不满足")

    # 页脚时间必须是北京时间（2026-11-27 22:40 这样的格式，且不能是 UTC 的清晨）
    idx = WEB / "index.html"
    if idx.exists():
        html = idx.read_text(encoding="utf-8")
        m = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) 生成", html)
        if not m:
            fails.append("index.html: 页脚没有「YYYY-MM-DD HH:MM 生成」")
        else:
            hour = int(m.group(1)[11:13])
            print(f"页脚时间：{m.group(1)}（北京时间应为 06:00–23:59 之间）")
            if hour < 5:
                print("  [warn] 小时数很小，可能在用 UTC —— 检查 render.now_cst()")

    print()
    if fails:
        for f in fails:
            print(f"[x] {f}")
        return 1
    print("[ok] 页面自检全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
