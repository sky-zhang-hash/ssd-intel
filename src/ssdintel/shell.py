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
        padding-bottom:var(--safe); }
  .nav a{ flex:1; display:flex; flex-direction:column; align-items:center; gap:3px;
          padding:9px 0 8px; text-decoration:none; color:var(--muted);
          font-size:12px; letter-spacing:.02em; -webkit-tap-highlight-color:transparent }
  .nav a.on{ color:var(--accent) }
  .nav svg{ width:22px; height:22px; stroke:currentColor; fill:none;
            stroke-width:1.7; stroke-linecap:round; stroke-linejoin:round }
  .nav a.on svg{ fill:color-mix(in srgb, var(--accent) 14%, transparent) }
  .fav{ background:none; border:0; padding:0; margin-left:2px; cursor:pointer;
        color:var(--muted); font-size:16px; line-height:1;
        min-width:30px; min-height:30px; display:inline-flex;
        align-items:center; justify-content:center;
        -webkit-tap-highlight-color:transparent }
  .fav[aria-pressed="true"]{ color:var(--accent) }
  .empty{ color:var(--muted); font-size:14px; padding:28px 0 }

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


def nav_html(active: str, root: str = "./") -> str:
    """active ∈ {today, archive, fav}；root 用于子目录页面的相对路径。"""
    items = (
        ("today", "今日", root + "index.html", ICON_TODAY),
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
      date: btn.dataset.date || ''
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
      return '<div class="point"><p class="pt-text">'
        + '<a href="' + esc(x.url) + '" target="_blank" rel="noopener">'
        + esc(x.title || x.url) + '</a></p>'
        + '<p class="meta"><span>' + esc(x.source) + ' · ' + esc(x.date) + '</span>'
        + '<button class="fav" data-url="' + esc(x.url) + '" data-title="'
        + esc(x.title) + '" data-source="' + esc(x.source) + '" data-date="'
        + esc(x.date) + '" aria-pressed="true" title="取消收藏">★</button></p></div>';
    }).join('');
    markAll();
  }

  markAll();
  renderFav();
})();
</script>
"""
