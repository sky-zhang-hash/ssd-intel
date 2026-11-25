# 微信读书 Cookie 守护（长期方案 A）
#
# 构建：docker compose build
# 首次扫码：docker compose run --rm keeper login
#   二维码会写到 ./data/qr.png，用微信扫；登录态存进 ./data/profile（持久化）
# 之后：docker compose up -d
#   每 12 小时抓一次新 Cookie，验证后写回仓库 secret WEREAD_COOKIE
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    KEEPER_DATA=/data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && python -m playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*

COPY keeper.py .

VOLUME ["/data"]

# 默认常驻；扫码时用 docker compose run --rm keeper login 覆盖
CMD ["python", "keeper.py", "daemon"]
