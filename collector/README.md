# 微信读书令牌守护（长期方案 A）

**它解决什么**：公众号没有公开接口，能拿到文章列表的唯一通道是微信读书的登录态，而这个登录态一两天就会过期。这个守护程序把那件事变成一次性的：**扫码登录一次**，之后它自己续期，并把新 Cookie 写回 GitHub 仓库的 `WEREAD_COOKIE` secret。

GitHub Actions 那边什么都不用改——它每天照旧读 secret，只是 secret 现在会自己更新。

## 两种跑法，二选一

| | 需要什么 | 适合 |
|---|---|---|
| **Windows 本机版**（`node/` + `setup-windows.cmd`） | Node.js 20+，不用装 Docker | 就拿这台 Windows 跑 |
| **Docker 版**（`Dockerfile` + `docker-compose.yml`） | Docker + 一台常开机器 | NAS / 小主机 / 旧笔记本 |

两台都支持，只是复用同一个 `data/` 目录（登录态、cookie、日志）。

---

## 一、Windows 本机版（推荐，双击就行）

**前提**：装好 Node.js 20+（[nodejs.org](https://nodejs.org)，一路下一步即可）。

**步骤**：

1. 去 GitHub 建一个**细粒度 token**：
   - Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new
   - Repository access：**Only select repositories** → 只选 `ssd-intel`
   - Permissions → Repository permissions → **Secrets: Read and write**（其它都不给）
   - 复制生成的 `github_pat_...`（只显示一次）

2. 双击 `collector/setup-windows.cmd`，跟着它走：
   - 自动 `npm install`
   - 弹出记事本让你填 `GITHUB_TOKEN`（粘进去保存关闭）
   - 弹出**浏览器窗口**，用微信扫码（扫完窗口自己关）
   - 自动注册每 12 小时跑一次的计划任务 `SSD-Weread-Keeper`

3. 验证：双击 `collector/status.cmd`，应看到

   ```
   2026-11-26 08:00:03  Cookie 有效，长度 227
   2026-11-26 08:00:04  已更新 secret WEREAD_COOKIE（key_id 1f2a3b4c…）
   ```

   然后去 GitHub 仓库 Settings → Secrets 看 `WEREAD_COOKIE` 的 **Updated** 时间是不是刚刚。

**日常**：
- 什么都不用做。
- 万一哪天日志说「登录态过期」，双击 `collector/update-cookie.cmd` 重新扫一次即可（几个月一次）。
- 取消自动续期：`schtasks /delete /tn "SSD-Weread-Keeper" /f`

---

## 二、Docker 版

```bash
cd ssd-intel/collector
cp .env.example .env        # 填 GITHUB_TOKEN 和 GITHUB_REPO
docker compose build        # 首次装 Chromium，3-5 分钟
docker compose run --rm keeper login
docker compose up -d        # 之后常驻，每 12 小时续一次
```

Docker 版用容器内的 Chromium（`playwright install chromium`），不需要宿主机的浏览器；二维码会存成 `data/qr.png`。

---

## 为什么这样就不会天天过期

之前手动复制的是 `wr_skey` 那一段**短期会话**，微信读书会把它跟 IP、设备绑定。你在本地和 GitHub 之间来回用同一个账号，它判异常就提前踢下线。

而这个守护程序：

1. 登录态活在浏览器 profile（`data/profile/`）里，是**长期**的；
2. 机器和出口 IP 稳定，只在一处登录；
3. 每轮只是从这个会话里**读取**当前有效的 cookie，不去别处重新登录。

## 一些细节

- `data/` 是全部状态（profile + cookie.txt + keeper.log），备份它就是备份登录态。**别提交进 git**（已在 `.gitignore`）。
- 只支持 Edge（Windows 自带）或 Chrome：`.env` 里 `BROWSER_CHANNEL=msedge|chrome`。
- 想改频率：`.env` 里 `INTERVAL_HOURS`，或改计划任务的 `/mo 12`。
- 验证 secret 是否写成功：`gh secret list`，或仓库 Settings → Secrets 的 Updated 列。

## 没有常开机器怎么办

走 B：手动续。`ssd-intel/README.md` 的「公众号」一节写了三步；只要**只在 GitHub 里用** Cookie（本地 `.env` 留空），寿命会比之前长一些。

## 排错：验证时返回 -2041 / -2010

| 错误码 | 含义 | 怎么办 |
|---|---|---|
| `-2010 用户不存在` | 浏览器里还没登录成功（扫码没完成或没点确认） | 重新 `login`，扫完在手机上点「确认登录」 |
| `-2012 登录超时` | Cookie 过期 | 重新 `login` |
| `-2041` | 该账号拿不到这个公众号（多数是**没在微信读书里关注这个号**，或是新账号无内容权限） | 用原来那个已关注 23 个号的账号登录；或在新账号的微信读书里逐个关注 |

诊断用的东西：`data\cookie.txt`（最新抓到的 Cookie）、`data\keeper.log`。
拿到 `cookie.txt` 后可以直接用 Python 打接口确认：

```python
import requests
ck = open("data/cookie.txt").read().strip()
h = {"Cookie": ck, "User-Agent": "Mozilla/5.0", "Origin": "https://weread.qq.com",
     "Referer": "https://weread.qq.com/"}
print(requests.get("https://weread.qq.com/web/shelf/sync", headers=h, timeout=20).text[:200])
print(requests.get("https://weread.qq.com/web/mp/articles",
                   params={"bookId": "MP_WXS_3095382082", "offset": 0}, headers=h, timeout=20).text[:200])
```
