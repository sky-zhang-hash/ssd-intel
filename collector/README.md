# 微信读书令牌守护（长期方案 A）

**它解决什么**：公众号没有公开接口，能拿到文章列表的唯一通道是微信读书的登录态，而这个登录态一两天就会过期。这个容器把那件事变成一次性的：**扫码登录一次**，之后它自己续期，并把新 Cookie 写回 GitHub 仓库的 `WEREAD_COOKIE` secret。

GitHub Actions 那边什么都不用改——它每天照旧读 secret，只是 secret 现在会自己更新。

## 需要什么

- 一台**常开的机器**：家里的旧笔记本 / NAS / 小主机 / 树莓派（4GB 内存够）。不需要公网 IP。
- Docker + Docker Compose。
- 一个 GitHub 细粒度 token：**只给这一个仓库、只给 Secrets 的读写权限**（Fine-grained token → Repository access: 只选 ssd-intel → Permissions: Secrets: Read and write）。它只存在这台机器上。

## 三步跑起来

```bash
cd ssd-intel/collector
cp .env.example .env        # 填 GITHUB_TOKEN 和 GITHUB_REPO

docker compose build        # 第一次会装 Chromium，约 3-5 分钟
docker compose run --rm keeper login
```

`login` 会打开微信读书首页，把登录二维码存成 `data/qr.png`：

```bash
# 在能看文件的机器上打开，或用 scp 拿下来
open data/qr.png        # macOS
start data\qr.png       # Windows
```

用手机微信扫码 → 容器会自己发现登录成功、验证 Cookie 真能拉到文章列表、写回 secret，然后退出。

```bash
docker compose up -d    # 之后常驻，每 12 小时续一次
```

## 怎么确认它在干活

```bash
docker compose logs -f keeper      # 看日志
docker compose exec keeper tail -f /data/keeper.log
```

正常的一轮长这样：

```
2026-11-26 08:00:03  Cookie 有效，长度 227
2026-11-26 08:00:04  已更新 secret WEREAD_COOKIE（key_id 1f2a3b4c…）
2026-11-26 08:00:04  睡 12 小时后继续
```

如果它说「登录态可能已失效」，重新跑一次 `docker compose run --rm keeper login` 扫码即可——**这种情况通常几个月才一次**，因为登录态是浏览器 profile 里的长期会话，不是那个短期 cookie。

## 为什么这样就不会天天过期

之前手动复制的是 `wr_skey` 那一段**短期会话**，微信读书会把它跟 IP、设备绑定，你在本地和 GitHub 之间来回用，它判异常就提前踢。而这里：

1. 登录态活在容器里的 Chromium profile（`data/profile`），是**长期**的；
2. 容器 IP 稳定，只在这一台机器上用一个账号；
3. 每轮只是从这个会话里**读取**当前有效的 cookie，不去别处登录。

## 一些细节

- `data/` 目录是全部状态（profile + cookie.txt + qr.png + keeper.log），备份它就是备份登录态。**别把它提交进 git**。
- 容器默认 `headless` 跑。如果你的机器上二维码取不到（微信读书改版），可以 `docker compose run --rm -e HEADLESS=0 keeper login` 配一个带显示的机器，或者直接看 `data/qr.png` 有没有生成。
- 想改频率就改 `INTERVAL_HOURS`（默认 12 小时）。cookie 有效期通常是几天，12 小时一次足够。
- 想验证它写的 secret 对不对：`gh secret list` 或 GitHub 仓库 Settings → Secrets 里看 `Updated` 时间。

## 没有常开机器怎么办

那就走 B：手动续。`ssd-intel/README.md` 的「公众号」一节写了手动复制 Cookie 的三步；只要**只在 GitHub 里用**这个 Cookie（本地 `.env` 留空），寿命会比之前长一些。
