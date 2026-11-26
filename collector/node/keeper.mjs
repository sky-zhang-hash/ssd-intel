#!/usr/bin/env node
/**
 * 微信读书 Cookie 守护（方案 A · 本机版，Node + Playwright）
 *
 * 为什么是 Node：这台机器上 Python 的 pip 被沙箱拦住，但 node/npm 能用。
 * 为什么不需要下载浏览器：Windows 自带 Edge，Playwright 可以直接驱动它
 * （channel: 'msedge'），省掉 130MB 的浏览器下载。
 *
 * 三种模式：
 *   node keeper.mjs login     首次：打开浏览器窗口，微信扫码登录，登录态存进 data/profile
 *   node keeper.mjs once      抓一次 Cookie → 验证 → 写回 GitHub secret（调试用）
 *   node keeper.mjs daemon    常驻，每 INTERVAL_HOURS 小时跑一次（默认 12）
 *
 * 需要 collector/node/.env（或环境变量）：
 *   GITHUB_TOKEN=ghp_xxx       细粒度 PAT，只给 ssd-intel 仓库的 Secrets 读写
 *   GITHUB_REPO=owner/repo
 */
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DATA = process.env.KEEPER_DATA || path.join(HERE, '..', 'data');
const PROFILE = path.join(DATA, 'profile');
const COOKIE_FILE = path.join(DATA, 'cookie.txt');
const LOG_FILE = path.join(DATA, 'keeper.log');

const SECRET_NAME = process.env.SECRET_NAME || 'WEREAD_COOKIE';
const BOOK_ID = process.env.BOOK_ID || 'MP_WXS_3095382082'; // 闪存市场
const INTERVAL_HOURS = Number(process.env.INTERVAL_HOURS || 12);
const CHANNEL = process.env.BROWSER_CHANNEL || 'msedge'; // msedge / chrome

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
         + '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';

function loadEnv() {
  const f = path.join(HERE, '.env');
  if (!fs.existsSync(f)) return;
  for (const line of fs.readFileSync(f, 'utf8').split(/\r?\n/)) {
    const s = line.trim();
    if (!s || s.startsWith('#') || !s.includes('=')) continue;
    const i = s.indexOf('=');
    const k = s.slice(0, i).trim();
    if (!process.env[k]) process.env[k] = s.slice(i + 1).trim();
  }
}

function log(msg) {
  const line = `${new Date().toLocaleString('zh-CN', { hour12: false })}  ${msg}`;
  console.log(line);
  try { fs.appendFileSync(LOG_FILE, line + '\n'); } catch { /* ignore */ }
}

async function openContext(headless) {
  fs.mkdirSync(PROFILE, { recursive: true });
  const opts = {
    headless,
    userAgent: UA,
    locale: 'zh-CN',
    viewport: { width: 480, height: 900 },
    args: ['--disable-blink-features=AutomationControlled'],
  };
  try {
    return await chromium.launchPersistentContext(PROFILE, { ...opts, channel: CHANNEL });
  } catch (e) {
    log(`启动 ${CHANNEL} 失败（${e.message.split('\n')[0]}），退回内置 chromium`);
    return await chromium.launchPersistentContext(PROFILE, opts);
  }
}

async function captureCookie(headless = true) {
  const ctx = await openContext(headless);
  const page = await ctx.newPage();
  let grabbed = '';
  page.on('request', (req) => {
    if (grabbed || !req.url().includes('weread.qq.com')) return;
    const ck = req.headers()['cookie'] || '';
    if (ck.includes('wr_vid=')) grabbed = ck;
  });
  await page.goto('https://weread.qq.com/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(4000);
  if (!grabbed) {
    const cookies = await ctx.cookies('https://weread.qq.com');
    grabbed = cookies.map((c) => `${c.name}=${c.value}`).join('; ');
  }
  await ctx.close();
  return grabbed;
}

async function verify(cookie) {
  if (!cookie) return false;
  try {
    const r = await fetch(
      `https://weread.qq.com/web/mp/articles?bookId=${BOOK_ID}&offset=0`,
      { headers: { Cookie: cookie, 'User-Agent': UA, Accept: 'application/json, text/plain, */*',
                   Origin: 'https://weread.qq.com', Referer: 'https://weread.qq.com/' } },
    );
    const text = await r.text();
    let data = {};
    try { data = JSON.parse(text); } catch { /* 非 JSON */ }
    const code = Number(data.errCode ?? data.errcode ?? 0);
    if (code === 0) return true;
    log(`验证失败：errCode=${code} ${data.errMsg || ''} | 原始: ${text.slice(0, 120)}`);
  } catch (e) {
    log(`验证异常：${e.message}`);
  }
  return false;
}

// 便宜的存活检查：书架接口不消耗「文章列表」的配额。
// 之前登录轮询每 4 秒打一次 /web/mp/articles，5 分钟打 70 多次，
// 直接把这个账号打到 -2041（频控，几小时才解）。所以登录只认书架。
async function alive(cookie) {
  if (!cookie) return false;
  try {
    const r = await fetch('https://weread.qq.com/web/shelf/sync', {
      headers: { Cookie: cookie, 'User-Agent': UA, Accept: 'application/json, text/plain, */*',
                 Origin: 'https://weread.qq.com', Referer: 'https://weread.qq.com/' },
    });
    const d = JSON.parse(await r.text());
    const code = Number(d.errCode ?? d.errcode ?? 0);
    return code === 0;
  } catch {
    return false;
  }
}

async function shelfInfo(cookie) {
  try {
    const r = await fetch('https://weread.qq.com/web/shelf/sync', {
      headers: { Cookie: cookie, 'User-Agent': UA, Accept: 'application/json, text/plain, */*',
                 Origin: 'https://weread.qq.com', Referer: 'https://weread.qq.com/' },
    });
    const t = await r.text();
    const d = JSON.parse(t);
    const code = Number(d.errCode ?? d.errcode ?? 0);
    if (code !== 0) return `shelf errCode=${code} ${d.errMsg || ''}`;
    const n = (d.books || []).filter((b) => String(b.bookId || '').startsWith('MP_WXS_')).length;
    return `登录 OK，书架 ${d.bookCount ?? 0} 本，其中公众号 ${n} 个`;
  } catch (e) {
    return `shelf 请求失败：${e.message}`;
  }
}

async function updateSecret(cookie) {
  const repo = process.env.GITHUB_REPO;
  const token = process.env.GITHUB_TOKEN;
  if (!repo || !token) { log('没配 GITHUB_REPO / GITHUB_TOKEN，只存本地文件'); return false; }
  try {
    const sodium = (await import('libsodium-wrappers')).default;
    await sodium.ready;
    const api = `https://api.github.com/repos/${repo}/actions/secrets`;
    const h = { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json',
                'User-Agent': 'ssd-intel-keeper' };
    const keyRes = await fetch(`${api}/public-key`, { headers: h });
    if (!keyRes.ok) { log(`取公钥失败 ${keyRes.status}`); return false; }
    const key = await keyRes.json();
    const pub = sodium.from_base64(key.key, sodium.base64_variants.ORIGINAL);
    const sealed = sodium.crypto_box_seal(sodium.from_string(cookie), pub);
    const put = await fetch(`${api}/${SECRET_NAME}`, {
      method: 'PUT',
      headers: { ...h, 'Content-Type': 'application/json' },
      body: JSON.stringify({ encrypted_value: sodium.to_base64(sealed, sodium.base64_variants.ORIGINAL),
                             key_id: key.key_id }),
    });
    if (put.status === 201 || put.status === 204) {
      log(`已更新 secret ${SECRET_NAME}（key_id ${key.key_id.slice(0, 8)}…）`);
      return true;
    }
    log(`写 secret 失败 ${put.status} ${(await put.text()).slice(0, 160)}`);
  } catch (e) {
    log(`写 secret 异常：${e.message}`);
  }
  return false;
}

async function refreshOnce(headless = true) {
  const cookie = await captureCookie(headless);
  if (!cookie) { log('没抓到 Cookie：登录态可能已失效，跑一次 node keeper.mjs login'); return false; }
  fs.mkdirSync(DATA, { recursive: true });
  fs.writeFileSync(COOKIE_FILE, cookie);
  const shelf = await shelfInfo(cookie);
  log(`登录态自检：${shelf}`);
  if (!(await alive(cookie))) {
    log('Cookie 抓到了但书架接口不认（登录态过期），需要重新扫码：node keeper.mjs login');
    return false;
  }
  log(`Cookie 有效，长度 ${cookie.length}`);
  if (!(await verify(cookie))) {
    log('书架能读，但文章列表接口返回频控/异常（-2041 常见）；cookie 仍然写回，等配额恢复即可');
  }
  await updateSecret(cookie);
  return true;
}

async function login() {
  log('打开浏览器窗口，请用微信扫码登录（这个窗口不要关）');
  let ctx;
  try {
    ctx = await openContext(false);
  } catch (e) {
    log(`浏览器启动失败：${e.message.split('\n')[0]}`);
    return false;
  }
  const page = await ctx.newPage();
  try {
    await page.goto('https://weread.qq.com/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  } catch (e) {
    log(`打开微信读书超时（${e.message.split('\n')[0]}），但窗口还在，可以手动刷新页面再扫码`);
  }
  const deadline = Date.now() + 5 * 60 * 1000;
  let cookie = '';
  let dumped = false;
  while (Date.now() < deadline) {
    try {
      const cookies = await ctx.cookies('https://weread.qq.com');
      cookie = cookies.map((c) => `${c.name}=${c.value}`).join('; ');
      if (cookie.includes('wr_skey=') && cookie.includes('wr_vid=')) {
        fs.mkdirSync(DATA, { recursive: true });
        fs.writeFileSync(COOKIE_FILE, cookie);
        if (!dumped) {
          dumped = true;
          log(`已抓到登录态 Cookie（长度 ${cookie.length}），${await shelfInfo(cookie)}`);
        }
        // 用书架判断登录完成，避免把文章列表接口打到频控
        if (await alive(cookie)) {
          log('登录态已建立');
          break;
        }
      }
    } catch (e) {
      log(`轮询出错（继续等）：${e.message.split('\n')[0]}`);
    }
    await page.waitForTimeout(4000).catch(() => {});
  }
  await ctx.close().catch(() => {});
  if (!cookie || !(await alive(cookie))) {
    log('登录没成功（等了 5 分钟）');
    return false;
  }
  fs.mkdirSync(DATA, { recursive: true });
  fs.writeFileSync(COOKIE_FILE, cookie);
  await updateSecret(cookie);
  log('登录完成，Cookie 已保存并写回 secret');
  return true;
}

async function main() {
  loadEnv();
  fs.mkdirSync(DATA, { recursive: true });
  const mode = process.argv[2] || 'daemon';
  if (mode === 'login') return (await login()) ? 0 : 1;
  if (mode === 'once') return (await refreshOnce(true)) ? 0 : 1;
  if (mode === 'dump') {
    const ck = await captureCookie(true);
    if (!ck) { log('没抓到 Cookie'); return 1; }
    fs.writeFileSync(COOKIE_FILE, ck);
    log(`Cookie 已写入 ${COOKIE_FILE}（长度 ${ck.length}）`);
    log(`书架自检：${await shelfInfo(ck)}`);
    return 0;
  }
  if (mode === 'daemon') {
    for (;;) {
      try { await refreshOnce(true); } catch (e) { log(`本轮异常：${e.message}`); }
      log(`睡 ${INTERVAL_HOURS} 小时后继续`);
      await new Promise((r) => setTimeout(r, INTERVAL_HOURS * 3600 * 1000));
    }
  }
  console.log('用法：node keeper.mjs login | once | daemon');
  return 2;
}

main().then((c) => process.exit(c)).catch((e) => {
  log(`致命错误：${e && e.stack ? e.stack : e}`);
  process.exit(1);
});
