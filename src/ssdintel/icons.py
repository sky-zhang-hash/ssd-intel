"""生成 PWA 图标 PNG。

iOS 的 apple-touch-icon 与 Android 的安装图标都不认 SVG，只认 PNG，
所以这里用 Pillow 把 icon.svg 的造型重画成位图（4 倍超采样再缩，边缘才干净）。
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

ACCENT = "#2457F5"
SIZES = (180, 192, 512)
MASKABLE = 512  # 给 Android 自适应图标用的安全区版本


def _draw(size: int, *, safe_zone: bool = False) -> Image.Image:
    """按 512 坐标系画图；safe_zone=True 时整体缩到 80% 留给圆形裁切。"""
    scale = 4
    px = size * scale
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    k = px / 512.0
    if safe_zone:
        k *= 0.8

    def r(v: float) -> int:
        return round(v * k)

    # 底：圆角方块（maskable 版本铺满，让系统自己裁）
    radius = 0 if safe_zone else r(112)
    offset = (px - round(512 * k)) // 2
    d.rounded_rectangle(
        [offset, offset, offset + round(512 * k), offset + round(512 * k)],
        radius=radius,
        fill=ACCENT,
    )

    # 盘体外框
    d.rounded_rectangle(
        [offset + r(150), offset + r(120), offset + r(362), offset + r(392)],
        radius=r(28),
        outline="white",
        width=max(1, r(26)),
    )

    # 三条容量条，越往下越淡
    for y, w, alpha in ((176, 120, 255), (238, 120, 140), (300, 72, 90)):
        layer = Image.new("RGBA", (px, px), (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle(
            [offset + r(196), offset + r(y), offset + r(196 + w), offset + r(y + 26)],
            radius=r(13),
            fill=(255, 255, 255, alpha),
        )
        img = Image.alpha_composite(img, layer)

    return img.resize((size, size), Image.LANCZOS)


def png(size: int, *, safe_zone: bool = False) -> bytes:
    buf = io.BytesIO()
    _draw(size, safe_zone=safe_zone).save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def all_icons() -> dict[str, bytes]:
    """文件名 -> PNG 字节。"""
    out = {f"icon-{s}.png": png(s) for s in SIZES}
    out["icon-maskable.png"] = png(MASKABLE, safe_zone=True)
    return out
