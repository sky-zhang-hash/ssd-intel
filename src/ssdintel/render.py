"""渲染静态页面：日报 HTML + PWA manifest + 图标。"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import icons, shell

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
    "lang": "zh-CN",
    "start_url": "./index.html",
    "scope": "./",
    "display": "standalone",
    "orientation": "portrait",
    "background_color": "#fbfbf9",
    "theme_color": "#0f766e",
    "icons": [
        {"src": "./icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
        {"src": "./icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "./icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": "./icon-maskable.png", "sizes": "512x512", "type": "image/png",
         "purpose": "maskable"},
    ],
}


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TPL_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render(report: dict, out_dir: str | Path, stats: dict | None = None,
           archive: bool = True, reports: list[dict] | None = None) -> Path:
    """生成三屏 PWA：今日（index）/ 归档 / 收藏，外加子目录里的历史页。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    env = _env()
    base_ctx = {
        "nav_css": shell.NAV_CSS,
        "fav_js": shell.FAV_JS,
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    def page(tpl: str, active: str, root: str, **ctx) -> str:
        return env.get_template(tpl).render(
            **base_ctx, **ctx,
            nav=shell.nav_html(active, root), root=root,
        )

    # 今日
    index = out / "index.html"
    index.write_text(page(
        "report.html.j2", "today", "./",
        r=report, stats=stats or {},
    ), encoding="utf-8")

    # 历史页（放在 d/ 下，根路径要回退一级）
    if archive:
        d = out / "d"
        d.mkdir(exist_ok=True)
        day_html = page("report.html.j2", "today", "../", r=report, stats=stats or {})
        (d / f"{report['date']}.html").write_text(day_html, encoding="utf-8")

    # 归档列表：优先用数据库里的各期标题（有 headline 才好看），没有就退回文件名
    rows = list(reports or [])
    if archive and not rows:
        d = out / "d"
        rows = [{"date": p.stem, "headline": ""}
                for p in sorted(d.glob("*.html"), reverse=True) if p.name != "index.html"]
    archive_html = page("archive.html.j2", "archive", "./", reports=rows)
    (out / "archive.html").write_text(archive_html, encoding="utf-8")
    if archive:
        # 老链接 /d/index.html 别断，直接指向新归档页
        (out / "d" / "index.html").write_text(
            '<!doctype html><meta charset="utf-8">'
            '<meta http-equiv="refresh" content="0; url=../archive.html">'
            '<a href="../archive.html">归档</a>', encoding="utf-8")

    # 收藏（纯前端渲染，无服务端数据）
    (out / "fav.html").write_text(
        page("fav.html.j2", "fav", "./"), encoding="utf-8")

    (out / "manifest.webmanifest").write_text(
        json.dumps(MANIFEST, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "icon.svg").write_text(ICON_SVG, encoding="utf-8")
    for name, data in icons.all_icons().items():
        (out / name).write_bytes(data)

    # PWA：service worker 做外壳缓存——断网也能看到最近一次打开的那屏
    (out / "sw.js").write_text(
        "const C='ssd-intel-v2';"
        "const SHELL=['./index.html','./archive.html','./fav.html','./manifest.webmanifest'];"
        "self.addEventListener('install',e=>e.waitUntil("
        "caches.open(C).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting())));"
        "self.addEventListener('activate',e=>e.waitUntil("
        "caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==C).map(k=>caches.delete(k))))));"
        "self.addEventListener('fetch',e=>{"
        "if(e.request.method!=='GET')return;"
        "e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request).then(resp=>{"
        "const cp=resp.clone();caches.open(C).then(c=>c.put(e.request,cp));return resp;"
        "}).catch(()=>caches.match('./index.html'))))});",
        encoding="utf-8",
    )

    print(f"  [render] {index}")
    return index
