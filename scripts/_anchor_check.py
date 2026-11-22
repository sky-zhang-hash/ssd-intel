import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, "ssd-intel/src")
from ssdintel import score
from ssdintel.models import Store

rules = score.load_rules("ssd-intel/config/keywords.yaml")
rules["categories"] = rules["categories"]
anchors = rules["anchors"]

store = Store("ssd-intel/data/ssdintel.db")
items = store.recent(hours=36)
for it in items:
    text = f"{it.title} {it.summary}"
    hits = [a for a in anchors if score._match(a, text)]
    ex = [e for e in rules["exclude"] if score._match(e, text)]
    print(f"{it.score:5.2f} | anchors={hits} | excl={ex} | {it.title[:50]}")
    if not hits:
        print("        !! 没有锚点却被保留，摘要:", it.summary[:150])
