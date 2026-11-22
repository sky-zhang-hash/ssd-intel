"""移动端三屏结构的公共骨架：今日 / 归档 / 收藏，底部固定导航。

设计取舍：
- 三屏都是静态页，收藏只能存在**手机本地**（localStorage），不做后端——
  用户自用、数据公开，没必要为此上一个需要登录的服务。
- 导航用固定底栏 + `env(safe-area-inset-bottom)`，iPhone 的横条不会压住内容；
  底部同时给 body 留出 `--nav-h` 的 padding，滚到底也看不全的问题就此消失。
- 三个页面共用一份 CSS，避免字号/间距各写一套后走形。
"""

from __future__ import annotations

# 底栏高 56px + 安全区，body 的 padding-bottom 引用同一个变量
NAV_CSS = """
  :root{ --nav-h:56px; --safe:env(safe-area-inset-bottom,0px); }
  body{ padding-bottom:calc(var(--nav-h) + var(--safe) + 28px) }
  .nav{ position:fixed; left:0; right:0; bottom:0; z-index:50;
        display:flex; background:var(--card); border-top:1px solid var(--line);
        box-shadow:0 -1px 3px rgba(15,23,42,.06);
        padding-bottom:var(--safe); }
  .nav a{ flex:1; display:flex; flex-direction:column; align-items:center; gap:3px;
          padding:8px 0 7px; text-decoration:none; color:var(--muted);
          font-size:13px; letter-spacing:.02em; -webkit-tap-highlight-color:transparent }
  .nav a.on{ color:var(--accent) }
  .nav svg{ width:22px; height:22px; stroke:currentColor; fill:none;
            stroke-width:1.7; stroke-linecap:round; stroke-linejoin:round }
  .nav a.on svg{ fill:color-mix(in srgb, var(--accent) 14%, transparent) }
  .fav{ background:none; border:0; padding:0; margin-left:2px; cursor:pointer;
        color:var(--muted); font-size:17px; line-height:1;
        min-width:30px; min-height:30px; display:inline-flex;
        align-items:center; justify-content:center;
        -webkit-tap-highlight-color:transparent }
  .fav[aria-pressed="true"]{ color:var(--accent) }
  .empty{ color:var(--muted); font-size:16px; line-height:1.7; padding:26px 0 }

  @media (prefers-color-scheme: dark){
    .nav{ background:var(--card) }
  }
"""

# 三个图标用同一套线性风格，尺寸/线宽由 CSS 控制
ICON_TODAY = ('<svg viewBox="0 0 24 24"><path d="M4 5h16v14H4z"/><path d="M7 9h7M7 13h10M7 17h5"/></svg>')
ICON_ARCHIVE = ('<svg viewBox="0 0 24 24"><path d="M4 7h16v3H4z"/>'
                '<path d="M5 10v9h14v-9"/><path d="M10 14h4"/></svg>')
ICON_FAV = ('<svg viewBox="0 0 24 24"><path d="M12 5.5l2.1 4.3 4.7.7-3.4 3.3.8 4.7'
            '-4.2-2.2-4.2 2.2.8-4.7L4.9 10.5l4.7-.7z"/></svg>')
ICON_ALL = ('<svg viewBox="0 0 24 24"><path d="M4 6h16M4 12h16M4 18h10"/></svg>')


def nav_html(active: str, root: str = "./") -> str:
    """active ∈ {today, all, archive, fav}；root 用于子目录页面的相对路径。"""
    items = (
        ("today", "今日", root + "index.html", ICON_TODAY),
        ("all", "全部", root + "all.html", ICON_ALL),
        ("archive", "归档", root + "archive.html", ICON_ARCHIVE),
        ("fav", "收藏", root + "fav.html", ICON_FAV),
    )
    links = "".join(
        f'<a href="{href}"{" class=\"on\"" if key == active else ""}>'
        f'{svg}<span>{label}</span></a>'
        for key, label, href, svg in items
    )
    return f'<nav class="nav">{links}</nav>'


# 收藏按钮 + 读写逻辑。fav.html 复用同一份 script，所以抽出来。
# 用事件委托而不是逐个 addEventListener —— 收藏页的条目是渲染后才出现的，
# 逐个绑定会漏，导致「能收藏、不能在收藏页取消」。
FAV_JS = """
<script>
(function(){
  var KEY = 'ssd.fav.v1';
  function load(){
    try { return JSON.parse(localStorage.getItem(KEY) || '[]'); } catch(e){ return []; }
  }
  function save(list){
    try { localStorage.setItem(KEY, JSON.stringify(list)); } catch(e){}
  }
  function mark(btn, on){
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    btn.textContent = on ? '★' : '☆';
    btn.title = on ? '取消收藏' : '收藏';
  }
  function markAll(){
    var saved = load().map(function(x){ return x.url; });
    document.querySelectorAll('.fav').forEach(function(b){
      mark(b, saved.indexOf(b.dataset.url || '') >= 0);
    });
  }

  document.addEventListener('click', function(e){
    var btn = e.target.closest ? e.target.closest('.fav') : null;
    if (!btn) return;
    e.preventDefault();
    var url = btn.dataset.url || '';
    if (!url) return;
    var list = load();
    var i = -1;
    for (var k = 0; k < list.length; k++) if (list[k].url === url) { i = k; break; }
    if (i >= 0) list.splice(i, 1);
    else list.unshift({
      url: url,
      title: btn.dataset.title || '',
      source: btn.dataset.source || '',
      date: btn.dataset.date || '',
      time: btn.dataset.time || ''
    });
    save(list);
    mark(btn, i < 0);
    // 在收藏页取消收藏时，把那条直接摘掉
    if (i >= 0) {
      var row = btn.closest('.point');
      if (row && document.querySelector('#fav-list')) {
        row.parentNode.removeChild(row);
        if (!document.querySelector('#fav-list .point')) renderFav();
      }
    }
  });

  function esc(s){
    return String(s || '').replace(/[<>&"]/g, function(c){
      return {'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c];
    });
  }

  function renderFav(){
    var list = document.querySelector('#fav-list');
    if (!list) return;
    var items = load();
    if (!items.length){
      list.innerHTML = '<p class="empty">还没有收藏。在今日日报里点条目右侧的 ☆ 就能存到这里。</p>';
      return;
    }
    list.innerHTML = items.map(function(x){
      var when = x.time || x.date || '';
      return '<div class="point"><p class="pt-text">'
        + '<a href="' + esc(x.url) + '" target="_blank" rel="noopener">'
        + esc(x.title || x.url) + '</a></p>'
        + '<p class="meta"><a class="src" href="' + esc(x.url) + '" target="_blank" rel="noopener">'
        + '<span class="lbl">' + esc(x.source) + (when ? '<span class="when">' + esc(when)
        + '</span>' : '') + '<span class="ext">↗</span></span></a>'
        + '<button class="fav" data-url="' + esc(x.url) + '" data-title="'
        + esc(x.title) + '" data-source="' + esc(x.source) + '" data-date="'
        + esc(x.date) + '" data-time="' + esc(x.time) + '"'
        + ' aria-pressed="true" title="取消收藏">★</button></p></div>';
    }).join('');
    markAll();
  }

  markAll();
  renderFav();
})();
</script>
"""

# 下拉刷新：静态站没法「重新采集」，所以这里做的是「检查有没有新版本」——
# 拉一次当前页、比对 <meta name="built">，比到新的就重载。
# 附加价值：顺便让 Service Worker 调一次 update()，不用等它自己轮询。
PULL_CSS = """
  #pull{position:fixed;left:0;right:0;top:0;z-index:60;pointer-events:none;
        display:flex;justify-content:center;align-items:flex-end;
        height:56px;transform:translateY(-56px);opacity:0;
        transition:transform .18s ease, opacity .18s ease;
        font-size:14px;color:var(--muted)}
  #pull.on{transform:translateY(0)}
  #pull span{background:var(--card);border:1px solid var(--line);
             box-shadow:var(--shadow);border-radius:999px;padding:6px 14px}
"""

PULL_JS = """
<div id="pull"><span>下拉刷新</span></div>
<script>
(function(){
  var el = document.getElementById('pull');
  var label = el ? el.querySelector('span') : null;
  if (!el || !label) return;

  var startY = 0, pulling = false, dist = 0, busy = false;
  var TRIGGER = 56;

  function show(text){
    label.textContent = text;
    el.classList.add('on');
  }
  function hide(){
    el.classList.remove('on');
  }

  function built(){
    var m = document.querySelector('meta[name="built"]');
    return m ? m.content : '';
  }

  function check(){
    busy = true;
    show('正在检查新版本…');
    var before = built();
    var jobs = [];
    try {
      jobs.push(navigator.serviceWorker.getRegistrations().then(function(regs){
        return Promise.all(regs.map(function(r){ return r.update(); }));
      }));
    } catch(e){}
    jobs.push(fetch(location.href.split('#')[0], {cache:'no-store'})
      .then(function(r){ return r.text(); })
      .then(function(html){
        var m = html.match(/<meta name="built" content="([^"]*)"/);
        var after = m ? m[1] : '';
        if (after && after !== before) {
          show('有新版本，正在更新…');
          setTimeout(function(){ location.reload(); }, 350);
          return 'reload';
        }
        show('已经是最新（' + (after || before) + ' 生成）');
        setTimeout(hide, 1800);
      })
      .catch(function(error){
        show('网络不通，稍后再试');
        setTimeout(hide, 1800);
      }));
    Promise.all(jobs).catch(function(){}).then(function(){ busy = false; });
  }

  document.addEventListener('touchstart', function(e){
    if (busy || window.scrollY > 2 || e.touches.length !== 1) return;
    startY = e.touches[0].clientY;
    pulling = true;
    dist = 0;
  }, {passive:true});

  document.addEventListener('touchmove', function(e){
    if (!pulling) return;
    var dy = e.touches[0].clientY - startY;
    if (dy <= 0) { pulling = false; hide(); return; }
    dist = Math.min(dy * 0.55, 96);
    el.style.transform = 'translateY(' + (dist - 56) + 'px)';
    el.style.opacity = Math.min(1, dist / TRIGGER);
    label.textContent = dist >= TRIGGER ? '松手刷新' : '下拉刷新';
  }, {passive:true});

  function end(){
    if (!pulling) return;
    pulling = false;
    el.style.transform = '';
    el.style.opacity = '';
    if (dist >= TRIGGER) { check(); } else { hide(); }
  }
  document.addEventListener('touchend', end, {passive:true});
  document.addEventListener('touchcancel', end, {passive:true});

  // 电脑上没有下拉手势，放一个等价的文字链接（手机上不显示）
  if (!('ontouchstart' in window)) {
    var wrap = document.querySelector('.wrap');
    if (wrap) {
      var p = document.createElement('p');
      p.className = 'footlink';
      var a = document.createElement('a');
      a.href = '#';
      a.textContent = '检查更新';
      a.addEventListener('click', function(ev){ ev.preventDefault(); check(); });
      p.appendChild(a);
      wrap.appendChild(p);
    }
  }
})();
</script>
"""
