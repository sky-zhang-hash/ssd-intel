# SSD 情报日报

每天早上把 SSD 相关的公开信息过一遍，挑出**产品侧**真正重要的，出一页能装在手机主屏上的日报。

不看价格行情，只看：谁出了什么主控、什么颗粒、谁在扩产封装、什么新品要上、AI 在怎么改变这块市场。

---

## 上线前三项自检（每次改动都要跑）

```bash
python scripts/audit_bookids.py        # 公众号名字 ↔ bookId 对不对得上（逐个向服务端核对）
python scripts/audit_links.py --n 8    # 库里公众号链接是不是真能打开（>100KB 才算正常页）
python scripts/audit_pages.py          # 转义 / 版本标记 / 刷新按钮 / SW 注册 / 相对路径
```

三条全绿才 push + dispatch。每一条都对应一次真实事故，细节写在 `AGENTS.md`。

## 快速开始

```powershell
cd ssd-intel

# 1. 先看源还活着没（约 20 秒）
python scripts\verify_sources.py

# 2. 生成日报（只抓 RSS，最快，约 15 秒）
python run_daily.py --no-wechat --no-llm

# 3. 带上公众号（要先在 .env 里填 WEREAD_COOKIE，见「公众号那部分」）
python run_daily.py

# 4. 看结果
start web\index.html
```

手机上打开这个页面，浏览器菜单里选「添加到主屏幕」，之后就像一个 App。

---

## 它跑起来是什么样

```
 == 采集 · 2026-11-22 ==
  [rss] TechPowerUp               40 条  rss2.0
  [rss] Tom's Hardware            40 条  rss2.0
  [rss] StorageReview             30 条  rss2.0
  [rss] ServeTheHome               6 条  rss2.0
  [rss] 全球半导体观察                   15 条  rss
  [rss] 超能网                       40 条  rss2.0
  公众号：微信读书 · 23 个号
  [wx]  闪存市场             39 篇
  [wx]  集微网              149 篇
  [wx]  半导体行业联盟          104 篇
  ...
  [wx]  长江存储             21 篇

  原始 955 条（RSS 171 / 微信 784）
  过线 120 条，过时丢弃 87 条，跨源去重后 32 条
  新增入库 18 条
  最近 36h 共 33 条可汇总

== 生成日报 ==
  [render] ...\web\index.html
```

这是 2026-11-22 的真实一轮：6 个 RSS 源 + 23 个公众号，784 篇公众号文章过闸门后只剩 32 条，最后日报里 33 条素材（含库里没超过 36 小时的）。**公众号的量很大、噪音也大**，闸门就是干这个的，别关。

产出是**五屏的 PWA**（不是单个网页）：

| 页面 | 用途 |
|---|---|
| `web/index.html` | 今日日报（AI 摘要，每条带发布时间，点来源名到原文，可点 ☆ 收藏） |
| `web/all.html` | 全部素材：窗口内**所有**条目，按日期倒序，不摘要不排序（想看全量就看这屏） |
| `web/archive.html` | 归档列表，按日期回看任意一期 |
| `web/fav.html` | 收藏夹（存在手机本地 localStorage，不上传） |
| `web/install.html` | 装到手机的图文说明（iPhone / Android / 电脑，带二维码） |
| `web/d/<date>.html` | 每期日报的历史快照，从归档点进去 |

底部固定导航（今日 / 全部 / 归档 / 收藏）+ `manifest.webmanifest` + `apple-touch-icon`，**视觉**（专业科技 / 冷灰蓝）：tokens 全在 `src/ssdintel/templates/base.html.j2` 顶部的 `:root` 里，改那一块四屏一起变——底色 `#F5F7FB`、卡片 `#FFFFFF`、正文 `#0F172A`、次要 `#55657D`、分隔 `#E2E8F0`、主色 `#2457F5`（只给链接和主操作）、点缀 `#0F8F8E`（板块圆点、大字），文字版的点缀另压深成 `--accent-2-ink:#0A6E6D` 以满足 4.5:1 对比度；圆角 8px、阴影 `0 1px 3px rgba(15,23,42,.08)`、数字统一 `font-variant-numeric:tabular-nums`。正文 17px、条目正文 16.5px——手机上不眯眼。深色模式用同一套变量另给一组值。

所以在手机上「添加到主屏幕」之后是全屏、无地址栏、有图标的独立入口——
用起来和 App 一样，只是不用上架、不用审核。

**装到手机上**（各一次）：

- iPhone：Safari 打开站点 → 分享 → 「添加到主屏幕」
- Android：Chrome 打开 → 右上角 ⋮ → 「添加到主屏幕」/「安装应用」

图标是 `icon.svg` 加 180/192/512 的 PNG（iOS 不认 SVG，必须 PNG），
由 `src/ssdintel/icons.py` 用 Pillow 画出，`render()` 时自动写进 `web/`。


---

## 几个可选开关

| 参数 | 作用 | 什么时候用 |
|---|---|---|
| `--wechat-source weread` | 公众号走微信读书（默认） | 配好 Cookie 后就是这个 |
| `--wechat-source sogou` | 公众号走搜狗关键词 | 兜底，时效不好 |
| `--no-wechat` | 跳过公众号采集 | 只想快速看看 RSS |
| `--no-llm` | 不调模型，出原始清单 | 没配 API key，或想看原始素材 |
| `--hours 48` | 汇总最近 48 小时 | 隔了两天没看 |
| `--max-age 10` | 丢弃发布超过 10 天的条目 | 默认 10，`0` 关闭 |

### 接上模型（可选，但强烈建议）

没有 key 时降级成「按类别分组的标题清单」，程序不报错但读起来是生素材。
配了 key 就变成一句话说清重点的摘要。

```powershell
setx DEEPSEEK_API_KEY "sk-xxxx"
# 可选：换网关或换模型
setx DEEPSEEK_BASE_URL "https://api.deepseek.com"
setx DEEPSEEK_MODEL "deepseek-chat"
```

防幻觉做了两个硬约束：素材以 `[编号]` 喂给模型，模型只能引用编号不能写 URL；编号到链接的映射在本地完成，所以它编不出假链接。

---

## 源清单（实测状态，2026-11-22）

| 源 | 语言 | 状态 | 说明 |
|---|---|---|---|
| TechPowerUp | en | ✅ | 新品/主控/颗粒更新最快，量大 |
| Tom's Hardware | en | ✅ | 消费级 SSD 评测，量很大 |
| StorageReview | en | ✅ | 企业级 SSD 深度评测 |
| ServeTheHome | en | ✅ | 企业级存储、AI 服务器配置 |
| 全球半导体观察 | zh | ✅ | DRAM/NAND 产业与产能 |
| 超能网 | zh | ✅ | 消费硬件为主，靠打分过滤 |
| Blocks & Files | en | ❌ | 有反爬（PoW 挑战），requests 拿不到 |
| The Register | en | ❌ | 同上 |
| 闪存市场 | zh | ❌ | 无官方 RSS，走公众号 |
| 集微网 | zh | ❌ | 域名是 ijiwei.com，无 RSS，走公众号 |
| 慧荣 / 群联 / 长江存储 / 江波龙 | — | ⏳ | newsroom 无 RSS，待做列表页解析 |

失败的不删，留在 `config/sources.yaml` 里标 `enabled: false` 并注明原因，免得以后重复踩。

---

## 公众号那部分

这是整件事最难的地方。分三层：

### L1 搜狗关键词轮询（已实现，但**时效不达标**）

按 `config/wechat_accounts.yaml` 里的 `search_queries` 搜文章，结果里带公众号名、发布时间和摘要。

实测（`python scripts\measure_wechat.py`）：

```
合计 68 条
  7 天内      1 条   1.5%
  8-30 天     2 条   2.9%
  30 天以上   65 条   95.6%
```

搜狗按**相关度**排序，不是时间。时间排序参数 `tsn=1` 实测返回落地页，`ft`/`et` 时间过滤被忽略。所以「SSD 主控」搜出来的是 2019 年的《现役主流SSD主控介绍》，不是今天的新闻。

**结论：这一路只能当背景检索，撑不起每日新闻。** 程序默认用 `--max-age 10` 把旧文挡掉，所以开了也没几条文进来 —— 这是预期行为，不是 bug。

另外两个坑：
- **按账号列文章不可用** —— 搜「SSDFans」返回「暂无相关的官方认证订阅号」，未认证的服务号/个人号搜不到
- **文章真链难拿** —— 真链藏在 `/link?url=...` 后面，请求十几条就触发 IP 级反爬（返回验证码）且持续一段时间。所以程序只还原分数最高的 6 条，一遇拦截就停手

所以它现在只是备用路径，要用得显式指定 `--wechat-source sogou`。

### L2 微信读书（已实现，**默认走这条**）

微信读书把公众号当"书"来订阅，有正规的列表接口，返回**按时间倒序**的文章流（标题、摘要、发布时间、阅读数都有）。不装 Docker、不装 WeRSS、不装任何新依赖 —— 就 `src/ssdintel/weread.py` 一个文件，用的还是已经装好的 `requests`。

接口是照 [`rachelos/we-mp-rss`](https://github.com/rachelos/we-mp-rss) 的 `weread_mp` 模式逆出来的，实测（2026-11-22，4 个号）：

```
GET https://weread.qq.com/web/mp/articles?bookId=MP_WXS_xxx&offset=0   → 文章流，一页 20 组 / 20~39 篇
GET https://weread.qq.com/api/mp/cover?bookId=MP_WXS_xxx               → 只要最新一篇（兜底）
```

只用一次 Cookie 头就能拉，`x-wr-ticket` 新版已废弃。原文链接由 `originalId` 拼成 `mp.weixin.qq.com/s/{token}`，注意微信读书把 token 里的 `_` 写成了 `~`，代码里已换回来（不换会报"参数错误"）。

**bookId 怎么来**：微信读书 Web 端**没有**公众号搜索接口（`/web/search/global` 永远只返回书）。但

```
bookId = "MP_WXS_" + base64解码(公众号的 __biz)
```

`__biz` 就写在公众号任意一篇文章的链接里，是公开信息。所以有两条路，选一条：

**路 A（推荐，一条命令批量）**：在微信读书 App 里搜这些号 → 关注（会进书架），然后

```bash
python scripts\shelf_bookids.py
```

它读 `/web/shelf/sync` 把书架上所有 `MP_WXS_*` 写进 `config/wechat_bookids.yaml`，并告诉你清单里还缺哪几个。`--dry-run` 只打印不写文件。

**路 B（一个个来）**：手机上打开该公众号任意一篇文章 → 右上角 ⋯ → 复制链接 → 发给我/贴进命令：

```bash
python scripts\resolve_bookids.py --link "闪存市场=https://mp.weixin.qq.com/s/xxxx"
python scripts\resolve_bookids.py --links links.txt   # 每行 号名=链接
```

注意**别用搜狗的链接**（形如 `mp.weixin.qq.com/s?src=11&timestamp=...&signature=...`）—— 那种会被重定向到验证码页，拿不到 `__biz`，脚本会明确提示。

**Cookie 怎么取**：浏览器打开 https://weread.qq.com → 微信扫码登录 → F12 → Network → 点任意请求 → 复制 Request Headers 里 `Cookie:` 整串 → 写进 `ssd-intel/.env` 的 `WEREAD_COOKIE=`（从 `.env.example` 复制一份）。注意必须带 `wr_skey` / `wr_vid` / `wr_rt`，只有 `wr_gid`/`wr_fp` 那种匿名串会返回 `-2010 用户不存在`。

配好之后 `python run_daily.py` 就自动带上公众号了。实测一轮：23 个号共 784 篇。

Cookie 过期了会打印 `Cookie 失效或配额用完，重新复制一次 Cookie`，重做一次即可（`wr_rt` 一般能撑几个月）。


### L3 手动补录（100% 可靠）

每天花 2 分钟，把刷到的、系统漏掉的链接贴进 `data/manual.json`，下次生成自动带上。

### 试过但不可行的路径（别再重复）

| 方案 | 结果 |
|---|---|
| wechat2rss 公开服务 | 395 个号，一个存储号都没有（偏安全/开发） |
| Google News RSS | 本机 ConnectTimeout，连不上 |
| Bing 网页搜索 `format=rss` | 能拿结果，但 `filters` 时间过滤在 RSS 模式被忽略 |
| 百度新闻 `tn=news` | 返回 2.6KB 跳转页，无结果 |
| 搜狗 `tsn=1` 时间排序 | 返回落地页（带 cookie / Referer 也不行） |
| 厂商 newsroom RSS | 慧荣/群联/长江存储/江波龙均无 RSS，403 或返回 HTML |

---

## 三道闸门 + 一个前提

`config/keywords.yaml` 控制什么能进日报：

1. **exclude** —— 命中直接丢（招聘、抽奖、耳机评测这类纯噪音），匹配标题+摘要
2. **anchors** —— 标题里必须命中至少一个存储锚点词（SSD / NAND / 主控 / 颗粒 / 闪存 / 存储芯片 / HBM / DRAM …）
3. **core + min_score** —— 必须命中核心类别且 `Σ(类别权重) × 信源权重 ≥ 0.45`

第二道闸门有两个容易踩的细节，都是实测踩出来的：

- **锚点只匹配标题，不匹配摘要。** 主板评测的摘要里常有一句「支持两个 M.2 SSD 插槽」，拿摘要匹配会把整篇主板文章放进来。
- **锚点词必须够专。** 踩过的：「存储」会命中「2+4 存储配置」（NAS 稿）；`Flash` 会命中「DeepSeek V4.1 **Flash** expert」（律师自建 AI 服务器稿）；`controller` 会命中「风扇 controller」。所以词表里没有 PCIe、M.2、Flash、controller。

实测「超能网」的「OPPO Pad Air6 开售」会同时命中「产品（发布）」「AI」「供应链」共 1.43 分，但跟 SSD 无关 —— 三道闸门把这类挡在外面。2026-11-22 那轮：955 条原始素材（含 784 篇公众号）最后只进 32 条。

价格类刻意只给 0.20 权重且非 core —— 命中价格的条目不会单独成节，只作为一句话背景；如果这条已经出现在板块里，背景行就不再重复它。

---

## 目录

```
ssd-intel/
├── run_daily.py              主流程
├── requirements.txt          6 个依赖，全是常见的（Pillow 只用来画图标）
├── config/
│   ├── sources.yaml          RSS 源（含失败记录与原因）
│   ├── wechat_accounts.yaml  22 个公众号 + 搜索词 + 三级策略
│   ├── wechat_bookids.yaml   号名 → 微信读书 bookId（解出来的，不是手动填的）
│   └── keywords.yaml         分类词表、锚点、排除词、阈值
├── src/ssdintel/
│   ├── models.py             Item / Store（SQLite）
│   ├── fetch.py              RSS + 搜狗微信采集
│   ├── weread.py             微信读书采集（公众号，默认路径）
│   ├── feedparse.py          lxml 写的 RSS/Atom 解析器
│   ├── score.py              三道闸门 + 跨源去重
│   ├── report.py             组装日报（LLM 或降级）
│   ├── render.py             渲染五屏 HTML + PWA 文件
│   ├── shell.py              底部导航 / 收藏逻辑（五屏共用）
│   ├── icons.py              用 Pillow 画 PWA 图标 PNG
│   └── templates/
│       ├── base.html.j2      公共骨架（CSS、manifest、导航、收藏脚本）
│       ├── report.html.j2    今日 / 单期日报
│       ├── archive.html.j2   归档列表
│       └── fav.html.j2       收藏夹
├── scripts/
│   ├── verify_sources.py     源健康检查
│   ├── probe_feed.py         探测任意 feed 地址能不能用
│   ├── shelf_bookids.py      从微信读书书架批量读公众号 bookId
│   ├── resolve_bookids.py    从文章链接解析单个 bookId
│   ├── measure_wechat.py     量化搜狗结果的新鲜度（验证 L1 为什么不达标）
│   ├── inspect_db.py         看库里现在有什么
│   ├── _anchor_check.py      排查某条为什么被收/被丢（打印命中的锚点）
│   └── _test_fav.py          收藏逻辑的单元测试（node 假 DOM，13 个断言）
├── data/ssdintel.db          SQLite（自动建）
└── web/                      产出（index / archive / fav / d/<date> + PWA 资源）
```

---

## 调参

想让它更聚焦，改 `config/keywords.yaml`：调 `min_score`（调高更少更精）、加 `anchors`、加 `exclude`。

想加/换源，改 `config/sources.yaml`：

```yaml
- name: 某站
  url: https://example.com/feed
  enabled: true
  weight: 0.8      # 0-1，越高越容易进日报
  lang: zh
```

改完先探测再启用：

```powershell
python scripts\probe_feed.py https://example.com/feed
python scripts\verify_sources.py
```

---

## 部署：GitHub Actions + Pages

**已经上线**：https://sky-zhang-hash.github.io/ssd-intel/ （仓库 `sky-zhang-hash/ssd-intel`，
每天北京时间 08:10 自动跑；三个 secret 里的两个已配好）。

工作流在 `.github/workflows/daily.yml`，把 `web/` 发到 GitHub Pages。

四步（换机器重建时用）：
1. 把 `ssd-intel/` 目录本身当仓库根推上去（workflow 里的路径是按这个假设写的；如果你的仓库根是上一层，所有路径前要加 `ssd-intel/`）
2. 仓库 Settings → Secrets and variables → Actions，加两个 secret：
   - `DEEPSEEK_API_KEY` —— 摘要用
   - `WEREAD_COOKIE` —— 公众号用（就是本地 `.env` 里那串，直接粘）
3. Settings → Pages 的 Source 选 **GitHub Actions**
4. Actions 页手动跑一次，跑完就能用 Pages 的地址装到手机主屏

数据库和归档页用 `actions/cache` 跨天带着走，所以跨源去重、历史归档都还能用。

**注意**：`data/` 只活在 CI 缓存里，缓存一段时间没人碰会被回收，那之后就重新从零开始（不致命，只是少了历史去重依据）。真要长期存档，把 `data/ssdintel.db` 提交进仓库更稳。

本机手动跑（不想等 CI）也是同一条命令 `python run_daily.py`，只是不会自动发布。

---

## 公众号的两条长期路线

公众号没有公开接口，唯一能拿到「文章列表」的通道是微信读书的登录态，而这个登录态会过期。两条路二选一（也可以都留着）：

| 方案 | 做法 | 谁维护 | 失效后 |
|---|---|---|---|
| **A 自建续期守护** | `collector/` 里一个小容器，扫码一次，之后每 12 小时自动抓新 Cookie 并写回仓库 secret | 一台常开的机器（NAS/旧笔记本） | 几个月一次，重新扫码 |
| **B 手动续** | 浏览器里复制一次 Cookie，粘进 GitHub Secrets | 你，1-2 分钟 | 一两天到一周一次 |

不管走哪条，**cookie 失效时都不会空页**：程序会降级到不需要登录的 `/api/mp/cover`，把每个号最新一篇的标题和真实链接补进来（页面上那条红字会说明今天用的是兜底）。这条兜底就是方案 C，代码里始终开着的。

详细步骤见 `collector/README.md`。

## 已知限制

- **采集只能用 Python**：本机 `curl.exe` 报 `schannel: AcquireCredentialsHandle failed (SEC_E_NO_CREDENTIALS)`，`Invoke-WebRequest` 报「基础连接已经关闭」，是 schannel 凭证损坏，不是网络问题。用它们调试会得出错误结论。
- 搜狗反爬是 IP 级的，会持续一段时间。频率再降也没用，只能接受「真链只还原一部分」。
- **本机推不了 GitHub**：`git` 走 https 也挂在同一个 schannel 问题上，`gh-proxy` 镜像现在回 403。改走 `tools/push_ssd_intel.py`（Git Data API，`api.github.com` 是通的）——推一版 43 个文件约 15 秒。
- 微信读书只给标题 + 摘要（几十到一两百字），拿不到全文。对"只看结论"的用法够了。
- **公众号覆盖 = `config/wechat_bookids.yaml` 里解析出几个号**（现在 23 个，含额外的「中国闪存市场」）。没解析 bookId 的号不会被采集，`resolve_bookids.py --list` 能看到 `missing` 列表。
- 微信读书有频率上限：一晚反复调试会撞 `-2014 请求过于频繁`，代码会退避重试（30/60/120 秒）后本轮收工、已采到的照常入库，第二天自愈。
- 微信读书 Cookie 会过期（`wr_rt` 一般几个月）。失效时日志会直接说「Cookie 失效或配额用完」，换一串即可。
- 去重按归一化标题算，同一事件不同措辞的两篇稿子会都留下。
- LLM 输出偶尔带原稿记者的判断口吻，模板里已统一转成「影响：」前缀。

## 公众号文章列表：机制与现状（2026-11-28）

`/web/mp/articles` 对 Python 的 `requests` 一律返回 `-2041`，而同一 cookie 用浏览器/Node 的 `fetch` 能拿到 `errCode=0`。这不是账号限流，是客户端指纹层面的拦截。

因此分工是：

- `collector/node/keeper.mjs`（浏览器进程）每轮/每小时拉 23 个号的文章列表 → 写 `collector/data/wechat_latest.json` → 用 Contents API 推到仓库 `data/wechat_latest.json`
- `run_daily.py` 优先读这份快照（`weread.load_snapshot`，超过 8 小时算过期并打印原因），快照没有才退回接口/封面兜底
- 云端 CI 从仓库里读到同一份快照，所以**页面上的公众号条目来自浏览器抓到的那份列表**

判定快照是否新鲜：`keeper.log` 里 `文章列表已导出：N 个号 / M 篇`，以及仓库 `data/wechat_latest.json` 的 `fetched_at`。


**现状（2026-11-28 11:00）**：`/web/mp/articles` 对 23 个号全部返回 `-2041`，Python、Node、真实浏览器页面三种方式都一样，
说明是账号/接口层面的封禁。所以现在每天实际能拿到的是**每个号最新一篇**（封面 + 正文），23 个号里约 18 个有正文。
解封后不需要改代码：keeper 的导出快照会自动变成全量，云端直接读快照。
