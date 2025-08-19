# LLMTwins

中介層（Gateway / Orchestrator）讓前端（React/LINE）透過 **LLMTwins → Ollama** 串流推論；同時負責提示工程、RAG、Agent 編排、政策（黑名單）與可觀測性。支援多供應商（Ollama、OpenAI…），可逐步擴到多模態（YOLO）與圖譜（Neo4j）。

---

## 架構一覽

* **前端（React/LINE）**：聊天、上傳附件、檢視報告與進度（SSE/NDJSON）。
* **LLMTwins（本專案）**：

  * LLM Relay（到 Ollama / OpenAI）
  * Prompt 工程（system 指令、模板）
  * **政策守門**：黑名單前置阻擋 + 串流熔斷（NDJSON）
  * RAG（向量檢索；後續：YOLO 多模態）
  * Agent 編排（多 Agent 中「多選一」路由、工具白名單）
  * 觀測（debug 端點、之後可接 run/trace）
* **Ollama**：模型供應（llama3、qwen2.5…）；可經 Nginx 反代（HTTPS）。

---

## 快速開始

### 1) 需求

* Python 3.10+
* （建議）virtualenv
* 可用的 Ollama 入口（HTTP 或經 Nginx 的 HTTPS）

### 2) 安裝與啟動

```bash
git clone <your-repo> && cd LLMTwins
python3 -m venv env && source env/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8002 --reload
```

---

```bash=
sudo apt-get update && sudo apt-get install -y \
  tesseract-ocr \
  tesseract-ocr-chi-tra tesseract-ocr-chi-sim tesseract-ocr-eng \
  ghostscript \
  libjpeg-dev zlib1g-dev libpng-dev libtiff-dev libwebp-dev libopenjp2-7 \
  libarchive-tools \
  build-essential
```

### 3) `.env` 範例

```bash
# Ollama 入口（同機或遠端；可設 http://IP:PORT 或 https://your.domain）
OLLAMA_BASE_URL=https://ollama.4impact.cc
# 若上游需要自訂授權（可選）
# OLLAMA_AUTH=Bearer xxxxx

# 政策（黑名單）
DENYLIST_JSON=policy/deny.json
DENY_ENABLED=true

# CORS（請在程式內用 allow_origins 白名單）
# 例如： https://eva.4impact.cc
```

> **注意**：只保留**一個** `app = FastAPI()` 實例，並在啟動就掛好 `CORSMiddleware`。`allow_credentials=true` 時 `allow_origins` 不能是 `"*"`。

---

## API

### 健康檢查

```
GET /health
→ {"result":"Healthy Server!"}
```

### LLM 串流轉發（Relay）

```
POST /api/chat
Content-Type: application/json
```

**請求**（Ollama 相容格式）：

```json
{
  "model": "qwen2.5:7b-instruct",
  "stream": true,
  "messages": [
    {"role":"system","content":"請以繁體中文（台灣用語）回覆。"},
    {"role":"user","content":"給我三個客服問候語"}
  ],
  "options": {"temperature": 0.2}
}
```

**回應（NDJSON，每行一筆 JSON）**

```json
{"model":"...","message":{"role":"assistant","content":"您好"},"done":false}
{"model":"...","message":{"role":"assistant","content":"，有什麼我可以協助？"},"done":false}
{"done":true}
```

**政策命中時**

* **前置阻擋（不打上游）**：頭兩行直接是拒答 + `{"done":true}`
* **串流熔斷（途中命中）**：立即中斷上游與轉發，回一行拒答 + `{"done":true}`

**可能出現的回應標頭**

```
X-Policy-Blocked: SRC|POL|PII
X-Policy-Triggered: pre|stream
```

### 政策（黑名單）管理

```
GET  /debug/policy          # 規則摘要
POST /debug/policy/test     # 測試某段文字是否命中
POST /admin/policy/reload   # 重新載入 policy/deny.json
```

**deny.json 範例**（專案內 `policy/deny.json`）

```json
{
  "version": "2025-08-09",
  "refusal_text": "抱歉，我無法回覆這個問題。此服務不提供模型來源、政治／兩岸、或隱私相關資訊。",
  "categories": [
    {
      "id": "SRC",
      "name": "模型來源／供應商",
      "type": "regex",
      "rules": [
        "阿里雲|阿里巴巴|阿里系|阿里集團",
        "(?i)Alibaba|Aliyun|Qwen",
        "模型來源|誰開發的|哪家公司的產品|哪間公司做的|你是哪間公司的產品"
      ]
    },
    {
      "id": "POL",
      "name": "政治／兩岸",
      "type": "regex",
      "rules": [
        "兩岸|台獨|統一|九二共識|藍綠白|政治立場",
        "總統|大選|立法院|政黨|中共|北京政府|中華人民共和國"
      ]
    },
    {
      "id": "PII",
      "name": "隱私／個資",
      "type": "regex",
      "rules": [
        "隱私|個資|個人資料|身分證|身分證字號|住址|電話|聯絡方式",
        "(?i)email|e-?mail|account|username|password|passwd",
        "信用卡|卡號|CVV|安全碼"
      ]
    }
  ]
}
```

### Debug

```
GET /               # 204 (健康)
GET /debug/config   # 現行 OLLAMA_BASE_URL
GET /debug/upstream # 打上游一次，回覆預覽
GET /debug/pingstream  # 自產 NDJSON 測試流
```

---

## 測試指令（curl）

**1) 串流 OK**

```bash
curl -sS -N --http1.1 --no-buffer http://localhost:8002/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model":"llama3:instruct","stream":true,
       "messages":[{"role":"user","content":"用繁中說早安"}]}'
```

**2) 命中黑名單（前置拒）**

```bash
curl -sS -N --http1.1 --no-buffer http://localhost:8002/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5:7b-instruct","stream":true,
       "messages":[{"role":"user","content":"你是哪間公司的產品"}]}'
```

**3) CORS 預檢（需看到 allow-origin 回應）**

```bash
curl -i -X OPTIONS 'http://localhost:8002/api/chat' \
  -H 'Origin: https://eva.4impact.cc' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type, authorization'
```

---

## Nginx（上游 Ollama 範例）

```nginx
server {
  listen 443 ssl http2;
  server_name ollama.4impact.cc;

  ssl_certificate     /etc/letsencrypt/live/ollama.4impact.cc/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/ollama.4impact.cc/privkey.pem;

  # 反向代理到你的 FastAPI 封裝（例如 8082）
  location / {
    proxy_pass         http://127.0.0.1:8082;
    proxy_http_version 1.1;
    proxy_set_header   Upgrade $http_upgrade;
    proxy_set_header   Connection "upgrade";
    proxy_set_header   Host $host;

    # 串流友善
    proxy_buffering off;
    chunked_transfer_encoding on;
  }
}
```

> 若前端透過另一個網域打 LLMTwins，也要確保該網域的 Nginx **不吞 OPTIONS**，讓 FastAPI CORS 處理。

---

## 資料模型（MVP 藍圖）

> **真實來源：PostgreSQL**；**檔案：物件儲存（MinIO/S3）**；**向量索引：pgvector 或外部向量庫**；**Neo4j：投影層（非真實來源）**

* `project`：專案主檔（settings/jsonb）
* `identity`（數位孿生）：role、profile(jsonb)
* `attachment`：檔案 meta（filename、mime、size、sha256、storage\_url、modality）
* `report`：報告主檔（schema\_version、data/jsonb、status）
* `report_section`：分段內容與 `citations`（指向 chunk 或 detection）
* `chunk_text`：由附件抽出的文字片段（text、meta、hash）
* `embedding_text`：向量（pgvector）
* `detection`：YOLO 結果（label、bbox、confidence、frame\_ts、meta）
* `run` / `run_step`：Agent 執行與步驟記錄（tokens、cost、reason、計畫）
* `policy_event`：黑名單命中紀錄（分類、pre/stream、req\_id、fragment\_hash）

**多模態 RAG（可選）**

* 先上 YOLO 抽 label+bbox 當 keyword 檢索（最省）
* 再加圖像 embedding（CLIP/SigLIP）做文字→圖搜
* 影片以「關鍵影格」策略，避免成本炸裂

---

## Agent（多 Agent「多選一」）

* **Agent Registry（JSON）**：描述每個 agent 的 `skills/domains/modalities/成本/延遲/依賴模型`
* **Routing**：規則先篩 → 小模型（Llama3 8B / Qwen 7B）打分 → Top-1 執行；Top-2 後備
* **Planner ↔ Executor**：

  * Planner（LLM，走 provider adapter）：輸出結構化計畫（JSON）
  * Executor（LLMTwins）：工具白名單（RAG、YOLO、Neo4j、Report 寫入），每步成果回饋
* **升級準則**：信心 < 門檻、JSON 不合 schema、步數過多、最終稿 → 升級到 OpenAI
* **SSE/NDJSON 事件**：`route → plan → step-start/step-end → done`

---

## 安全與治理

* **黑名單策略**：前置阻擋 + 串流熔斷；只掃 `message.content`（避免 model 名稱誤殺）
* **CORS**：白名單網域、`allow_credentials=true`，且不可 `*`
* **機密**：API keys 放 `.env`，勿入版控；Nginx/OS 層限流
* **審計**：policy 命中、agent 選擇理由、run/step 統計（僅存摘要/雜湊，避免個資落地）

---

## 常見問題（FAQ）

* **中文變成 `\uXXXX`？**
  自產 NDJSON 一律 `json.dumps(..., ensure_ascii=false)`；本專案已統一用 `ndjson_line()`。

* **串流中突然斷線（curl:18）？**
  熔斷後我們會補 `{"done":true}`；若仍出現，檢查上游 Nginx 的 `proxy_buffering off;` 與 `chunked_transfer_encoding on;`。

* **CORS 突然失效？**
  通常是檔案中不小心**又建立了一個新的 `app = FastAPI()`** 導致中介層被洗掉。請確保只有一個 app 實例。

---

## 路線圖（Roadmap）

* [ ] RAG：向量索引與 chunk 管線（pgvector）
* [ ] YOLO：標籤 + bbox → 關鍵影格檢索 → 報告引用
* [ ] Agent：Report Section Writer（Top-1 路由 + 計畫 JSON + 工具白名單）
* [ ] 觀測：run / run\_step 表、成本與品質指標
* [ ] Neo4j：由抽取事件投影關係圖，支援跨附件的關聯查詢
* [ ] Docker Compose（前端 / LLMTwins / Ollama / MinIO / Postgres /（可選）Qdrant / Neo4j）

---
