# ---- base ----
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

# 安裝必要系統套件（如有需要可再加）
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential curl && \
    rm -rf /var/lib/apt/lists/*

# 先複製 requirements 以利用快取
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 複製程式碼
COPY . .

# 預設使用 uvicorn（正式環境不要 --reload）
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD curl -fsS http://localhost:8000/docs >/dev/null || exit 1

# 依你的檔案結構，入口是 server.py 裡的 app
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]

