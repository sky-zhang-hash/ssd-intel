import sys, json
sys.path.insert(0, r"ssd-intel\src")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from ssdintel import weread

payload = {
    "reviews": [{
        "createTime": 1763700000,
        "subReviews": [{
            "review": {
                "reviewId": "r1",
                "mpInfo": {
                    "title": "测试标题",
                    "originalId": "AbC~dEf-_12",
                    "content": "这是一段摘要",
                    "time": 1763700123,
                    "readNum": 1234,
                },
            }
        }],
    }]
}
arts = weread.parse_articles(payload)
print(json.dumps(arts, ensure_ascii=False, indent=2))
assert arts[0]["url"] == "https://mp.weixin.qq.com/s/AbC_dEf-_12", arts[0]["url"]
assert arts[0]["published"].startswith("2025-"), arts[0]["published"]
print("\nOK: 链接反转义 + 时间戳解析 正确")

# 错误码行为
try:
    weread._check({"errcode": -2014, "errmsg": "quota"})
except weread.WereadError as e:
    print("OK: 配额错误 →", e, "| retriable =", e.retriable)
