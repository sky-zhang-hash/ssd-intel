"""Run the favorites logic in node against a tiny DOM stub.

The stub lives in _tools/_fav_stub.js (ASCII only) and reads the actual
FAV_JS from _tools/_fav_logic.js, which this script writes out of shell.py.
Keeping the two apart avoids escaping the logic into a JS template string.
"""
import io
import subprocess
import sys

sys.path.insert(0, r'ssd-intel/src')
from ssdintel import shell  # noqa: E402

LOGIC = r'_tools/_fav_logic.js'
STUB = r'_tools/_fav_stub.js'

io.open(LOGIC, 'w', encoding='utf-8', newline='\n').write(shell.FAV_JS)

STUB_JS = r"""
const fs = require('fs');
const LOGIC = fs.readFileSync(process.argv[2], 'utf8')
  .replace(/<script>/g, '')
  .replace(/<\/script>/g, '');

function El(tag, cls) {
  this.tagName = tag; this.attrs = {}; this.children = [];
  this.dataset = {}; this.classList = cls || []; this.parentNode = null;
  this._html = ''; this._text = '';
}
El.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
El.prototype.getAttribute = function (k) {
  return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null;
};
El.prototype.addEventListener = function () {};
Object.defineProperty(El.prototype, 'textContent', {
  get: function () { return this._text; },
  set: function (v) { this._text = v; }
});
Object.defineProperty(El.prototype, 'innerHTML', {
  get: function () { return this._html; },
  set: function (v) { this._html = v; }
});
El.prototype.matches = function (sel) {
  if (sel === '.fav') return this.classList.indexOf('fav') >= 0;
  if (sel === '.point') return this.classList.indexOf('point') >= 0;
  return false;
};
El.prototype.closest = function (sel) {
  var n = this;
  while (n) { if (n.matches(sel)) return n; n = n.parentNode; }
  return null;
};
El.prototype.querySelectorAll = function (sel) {
  var out = [];
  (function walk(node) {
    node.children.forEach(function (c) {
      if (c.matches(sel)) out.push(c);
      walk(c);
    });
  })(this);
  return out;
};
El.prototype.removeChild = function (c) {
  this.children = this.children.filter(function (x) { return x !== c; });
  c.parentNode = null;
};

function makeDom(withFavList) {
  var store = {};
  var body = new El('body');
  var list = null;

  var article = new El('article', ['point']);
  var btn = new El('button', ['fav']);
  btn.dataset.url = 'https://example.com/a';
  btn.dataset.title = 'item A';
  btn.dataset.source = 'src';
  btn.dataset.date = '2026-11-22';
  btn.parentNode = article;
  article.children.push(btn);
  article.parentNode = body;
  body.children.push(article);

  if (withFavList) {
    list = new El('div');
    list.parentNode = body;
    body.children.push(list);
  }

  var listeners = [];
  global.localStorage = {
    getItem: function (k) {
      return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null;
    },
    setItem: function (k, v) { store[k] = String(v); }
  };
  global.document = {
    querySelectorAll: function (sel) { return body.querySelectorAll(sel); },
    querySelector: function (sel) {
      if (sel === '#fav-list') return list;
      return null;
    },
    addEventListener: function (t, fn) { listeners.push(fn); }
  };

  var api = {
    store: store,
    btn: btn,
    list: list,
    click: function (el) {
      listeners.forEach(function (fn) {
        fn({ target: el, preventDefault: function () {} });
      });
    },
    boot: function () { eval(LOGIC); }
  };
  return api;
}

var fails = 0;
function check(cond, msg) {
  console.log((cond ? 'PASS ' : 'FAIL ') + msg);
  if (!cond) fails++;
}
const STAR = String.fromCharCode(9733);
const HOLLOW = String.fromCharCode(9734);

// 1) today page: star, then unstar
var d = makeDom(false);
d.boot();
check(d.btn.getAttribute('aria-pressed') === 'false', 'today: starts unfavorited');
check(d.btn.textContent === HOLLOW, 'today: hollow star');
d.click(d.btn);
check(d.btn.getAttribute('aria-pressed') === 'true', 'today: click -> favorited');
check(d.btn.textContent === STAR, 'today: solid star');
var saved = JSON.parse(d.store['ssd.fav.v1']);
check(saved.length === 1 && saved[0].url === 'https://example.com/a', 'today: localStorage has 1 item');
check(saved[0].source === 'src' && saved[0].date === '2026-11-22', 'today: meta saved');
d.click(d.btn);
check(d.btn.getAttribute('aria-pressed') === 'false', 'today: click again -> unfavorited');
check(JSON.parse(d.store['ssd.fav.v1']).length === 0, 'today: localStorage cleared');

// 2) fav page: renders what was saved earlier
var f = makeDom(true);
f.store['ssd.fav.v1'] = JSON.stringify([{
  url: 'https://example.com/b', title: 'item B', source: 'src2', date: '2026-11-22'
}]);
f.boot();
check(f.list.innerHTML.indexOf('item B') >= 0, 'fav page: renders saved item');
check(f.list.innerHTML.indexOf('src2') >= 0, 'fav page: renders source');
check(f.list.innerHTML.indexOf(STAR) >= 0, 'fav page: solid star (can unfavorite)');
check(f.list.innerHTML.indexOf('class="fav"') >= 0, 'fav page: has fav button');

// 3) fav page with nothing saved
var e = makeDom(true);
e.boot();
check(e.list.innerHTML.indexOf('\u8fd8\u6ca1\u6709\u6536\u85cf') >= 0, 'fav page: empty state copy');

if (fails) { console.log(fails + ' assertion(s) failed'); process.exit(1); }
console.log('all passed');
"""

io.open(STUB, 'w', encoding='utf-8', newline='\n').write(STUB_JS)
r = subprocess.run(['node', STUB, LOGIC], capture_output=True, text=True,
                   encoding='utf-8', errors='replace')
print(r.stdout.strip())
if r.stderr.strip():
    print('--- stderr ---')
    print(r.stderr.strip()[:1500])
sys.exit(r.returncode)
