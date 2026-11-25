#!/usr/bin/env python3
"""微信读书 Cookie 守护（长期方案 A）。

它解决的问题：微信读书的登录态会过期，而公众号文章列表接口必须有登录态。
手动复制 Cookie 一两天就要来一次，很烦。这个守护程序做三件事：

1. 用**持久化的 Chromium 用户目录**（Docker 卷）保存登录态，扫码一次就长期有效；
2. 每次醒来用这个目录打开微信读书，从真实请求里抓**最新**的 Cookie；
3. 验证 Cookie 真能拉到文章列表后，用 GitHub API 把它写回仓库的
   `WEREAD_COOKIE` secret——这样 GitHub Actions 每天跑的时候拿到的是新 Cookie。

三种模式：
    python keeper.py login    首次扫码：把登录二维码存成 qr.png，等人扫
    python keeper.py once     抓一次 Cookie、验证、写 secret（调试用）
    python keeper.py daemon   常驻：每 12 小时做一次（默认）

环境变量（docker-compose 里给）：
    GITHUB_TOKEN    细粒度 PAT，只给这个仓库的 Secrets: Read and write
    GITHUB_REPO     owner/repo，如 sky-zhang-hash/ssd-intel
    SECRET_NAME     默认 WEREAD_COOKIE
    BOOK_ID         任一 bookId，用来验证 Cookie 是否真能拉到列表
    INTERVAL_HOURS  守护间隔，默认 12
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path

DATA = Path(os.environ.get("KEEPER_DATA")
            or ("/data" if Path("/data").is_dir() else Path(__file__).parent / "data"))
PROFILE = DATA / "profile"
COOKIE_FILE = DATA / "cookie.txt"
QR_FILE = DATA / "qr.png"
LOG_FILE = DATA / "keeper.log"

REPO = os.environ.get("GITHUB_REPO", "")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
SECRET_NAME = os.environ.get("SECRET_NAME", "WEREAD_COOKIE")
BOOK_ID = os.environ.get("BOOK_ID", "MP_WXS_3095382082")  # 闪存市场
INTERVAL_HOURS = float(os.environ.get("INTERVAL_HOURS", "12"))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------- 浏览器

def _browser(pw, headless: bool = True):
    """持久化 profile 的 Chromium：登录态留在这个目录里，容器重启也不丢。"""
    PROFILE.mkdir(parents=True, exist_ok=True)
    return pw.chromium.launch_persistent_context(
        str(PROFILE),
        headless=headless,
        user_agent=UA,
        locale="zh-CN",
        viewport={"width": 480, "height": 900},
    )


def capture_cookie(want_qr: bool = False) -> str:
    """打开微信读书，从真实请求头里抓最新 Cookie。want_qr 时顺便存登录二维码。"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        ctx = _browser(pw)
        page = ctx.new_page()
        grabbed: list[str] = []

        def on_request(req):
            if "weread.qq.com" in req.url and not grabbed:
                ck = req.headers.get("cookie") or ""
                if "wr_vid=" in ck:
                    grabbed.append(ck)

        page.on("request", on_request)
        page.goto("https://weread.qq.com/", wait_until="networkidle", timeout=60000)
        # 触发一次公众号接口（首页会打这个请求；不行就自己打）
        page.wait_for_timeout(2500)
        if want_qr and not grabbed:
            try:
                el = page.query_selector("img.qr img, .qrCode img, img[src^='data:image']")
                if el:
                    QR_FILE.write_bytes(el.screenshot())
                    log(f"二维码已保存：{QR_FILE}（用微信扫码）")
            except Exception as e:  # noqa: BLE001
                log(f"取二维码失败：{e}")

        cookie = grabbed[0] if grabbed else ""
        if not cookie:
            cookie = "; ".join(f"{c['name']}={c['value']}" for c in ctx.cookies()
                               if c["domain"].endswith("weread.qq.com"))
        ctx.close()
        return cookie


def wait_login(timeout_s: int = 300) -> str:
    """扫码模式：轮询直到 Cookie 能拉到文章列表。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        cookie = capture_cookie(want_qr=True)
        if cookie and verify(cookie):
            return cookie
        time.sleep(8)
    return ""


# ---------------------------------------------------------------- 验证

def verify(cookie: str) -> bool:
    """实打实请求一次列表接口，别拿过期 Cookie 当有效。"""
    if not cookie:
        return False
    try:
        import requests
    except ImportError:
        return False
    try:
        r = requests.get(
            "https://weread.qq.com/web/mp/articles",
            params={"bookId": BOOK_ID, "offset": 0},
            headers={"Cookie": cookie, "User-Agent": UA,
                     "Accept": "application/json, text/plain, */*",
                     "Origin": "https://weread.qq.com", "Referer": "https://weread.qq.com/"},
            timeout=25,
        )
        data = r.json()
        code = int(data.get("errCode") or data.get("errcode") or 0)
        if code == 0:
            return True
        log(f"验证失败：errCode={code} {data.get('errMsg') or ''}")
    except Exception as e:  # noqa: BLE001
        log(f"验证异常：{e}")
    return False


# ---------------------------------------------------------------- GitHub secret

def update_secret(cookie: str) -> bool:
    """用 GitHub API 把 Cookie 写回 Actions secret（需要 PyNaCl 做 sealed box）。"""
    if not (REPO and TOKEN):
        log("没配 GITHUB_REPO / GITHUB_TOKEN，只保存到本地文件")
        return False
    try:
        from nacl import encoding, public
        import requests
    except ImportError as e:
        log(f"缺依赖（{e}），无法写 secret；容器镜像里已装 pynacl，本地跑请 pip install pynacl")
        return False

    api = f"https://api.github.com/repos/{REPO}/actions/secrets"
    h = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"}
    r = requests.get(f"{api}/public-key", headers=h, timeout=30)
    if r.status_code != 200:
        log(f"取公钥失败：{r.status_code} {r.text[:160]}")
        return False
    key = r.json()

    pub = public.PublicKey(key["key"].encode(), encoding.Base64Encoder())
    sealed = public.SealedBox(pub).encrypt(cookie.encode())
    payload = {"encrypted_value": base64.b64encode(sealed).decode(), "key_id": key["key_id"]}

    r = requests.put(f"{api}/{SECRET_NAME}", headers=h, json=payload, timeout=30)
    if r.status_code in (201, 204):
        log(f"已更新 secret {SECRET_NAME}（key_id {key['key_id'][:8]}…）")
        return True
    log(f"更新 secret 失败：{r.status_code} {r.text[:200]}")
    return False


# ---------------------------------------------------------------- 主流程

def refresh_once() -> bool:
    cookie = capture_cookie()
    if not cookie:
        log("没抓到 Cookie：登录态可能已失效，跑一次 `docker compose run --rm keeper login`")
        return False
    COOKIE_FILE.write_text(cookie, encoding="utf-8")
    if not verify(cookie):
        log("Cookie 抓到了但接口不认（多半是登录态过期），需要重新扫码")
        return False
    log("Cookie 有效，长度 %d" % len(cookie))
    update_secret(cookie)
    return True


def daemon() -> None:
    interval = max(1.0, INTERVAL_HOURS) * 3600
    while True:
        try:
            refresh_once()
        except Exception as e:  # noqa: BLE001
            log(f"本轮异常：{e}")
        log(f"睡 {INTERVAL_HOURS:g} 小时后继续")
        time.sleep(interval)


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    mode = sys.argv[1] if len(sys.argv) > 1 else "daemon"
    if mode == "login":
        log("开始扫码登录：二维码写到 " + str(QR_FILE))
        cookie = wait_login()
        if not cookie:
            log("超时没等到登录成功")
            return 1
        COOKIE_FILE.write_text(cookie, encoding="utf-8")
        update_secret(cookie)
        log("登录完成，Cookie 已保存")
        return 0
    if mode == "once":
        return 0 if refresh_once() else 1
    if mode == "daemon":
        daemon()
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
