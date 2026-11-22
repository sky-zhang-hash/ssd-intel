"""渲染静态页面：日报 HTML + PWA manifest + 图标。"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TPL_DIR = Path(__file__).resolve().parent / "templates"

ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
<rect width="512" height="512" rx="112" fill="#0f766e"/>
<rect x="150" y="120" width="212" height="272" rx="28" fill="none" stroke="#fff" stroke-width="26"/>
<rect x="196" y="176" width="120" height="26" rx="13" fill="#fff"/>
<rect x="196" y="238" width="120" height="26" rx="13" fill="#fff" opacity=".55"/>
<rect x="196" y="300" width="72" height="26" rx="13" fill="#fff" opacity=".35"/>
</svg>"""

MANIFEST = {
    "name": "SSD 情报日报",
    "short_name": "SSD 日报",
    "start_url": "./index.html",
    "display": "standalone",
    "background_color": "#fbfbf9",
    "theme_color": "#0f766e",
    "icons": [{"src": "./icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"}],
}


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TPL_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render(report: dict, out_dir: str | Path, stats: dict | None = None,
           archive: bool = True) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    html_tpl = _env().get_template("report.html.j2")
    html = html_tpl.render(
        r=report,
        stats=stats or {},
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )

    index = out / "index.html"
    index.write_text(html, encoding="utf-8")

    if archive:
        d = out / "d"
        d.mkdir(exist_ok=True)
        (d / f"{report['date']}.html").write_text(html, encoding="utf-8")
        # 归档索引，方便回看
        (d / "index.html").write_text(_archive_index(out), encoding="utf-8")

    (out / "manifest.webmanifest").write_text(
        json.dumps(MANIFEST, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "icon.svg").write_text(ICON_SVG, encoding="utf-8")

    # PWA：service worker 只做最简单的离线兜底
    (out / "sw.js").write_text(
        "const C='ssd-intel-v1';"
        "self.addEventListener('install',e=>e.waitUntil(caches.open(C).then(c=>c.add('./index.html'))));"
        "self.addEventListener('fetch',e=>e.respondWith("
        "caches.match(e.request).then(r=>r||fetch(e.request))));",
        encoding="utf-8",
    )

    print(f"  [render] {index}")
    return index


def _archive_index(out: Path) -> str:
    d = out / "d"
    files = sorted((p.stem for p in d.glob("*.html") if p.name != "index.html"), reverse=True)
    rows = "\n".join(f'<li><a href="{f}.html">{f}</a></li>' for f in files)
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SSD 情报日报 · 归档</title>
<style>body{{font:16px/1.7 -apple-system,"PingFang SC","Microsoft YaHei",system-ui,sans-serif;
max-width:640px;margin:0 auto;padding:24px 20px 64px;color:#191b1f;background:#fbfbf9}}
h1{{font-size:20px}}a{{color:#0f766e}}li{{margin:8px 0}}</style></head>
<body><h1>归档</h1><ul>{rows or '<li>还没有历史日报</li>'}</ul>
<p><a href="../index.html">← 回到今日</a></p></body></html>"""
