# LLMTwins Next-Gen API 規格（草案 / zh-TW）

> 版本：v1-draft
> 更新：2025-08-10
> 範疇：Relay、Policy、RAG（多模態）、Agent Orchestration、Report、Observability、Projects/Identities

本文件為 **未來新架構** 的 API 設計草案，便於分階段實作與驗收。內容以 **Project 為邊界**，支援多租戶、串流（NDJSON）、多模態 RAG（含 YOLO 標籤/影格），以及 multi-agent 的「多選一」路由與同步/非同步執行。

---

## 0. 規約與慣例

* **Base URL**：`https://<llmtwins-domain>`（開發：`http://localhost:8002`）
* **版本路徑**：`/v1/...`
* **認證**：`Authorization: Bearer <token>`（未來可接入 OAuth/JWT）；
* **專案邊界**：所有請求需帶 `X-Project-Id: <project_id>`（或放於 body）
* **格式**：請求 `application/json`；串流回應 `application/x-ndjson`（每行一 JSON）
* **ID 風格**：`proj_`、`att_`、`chunk_`、`det_`、`run_`、`job_`、`rpt_`、`sec_` 前綴
* **時間**：RFC3339 UTC
* **錯誤**：非串流→ `{ "error": "...", "code": "..." }`；串流→ `{"event":"error","data":{...}}` 後 `{"event":"done"}`

---

## 1. Projects / Identities（租戶與數位孿生）

### 1.1 建立專案

`POST /v1/projects`

```json
{ "name": "esg-demo", "settings": {"locale":"zh-TW"} }
```

**200** → `{ "id":"proj_...", "name":"esg-demo", "settings":{...} }`

### 1.2 取得/列表/成員

`GET /v1/projects/:id`
`GET /v1/projects`
`GET /v1/projects/:id/members`

### 1.3 數位孿生（Identity）

`POST /v1/identities`

```json
{ "project_id":"proj_...", "name":"agent_esg", "role":"writer", "profile": {"style":"concise"} }
```

---

## 2. Attachments（檔案庫與處理管線）

### 2.1 上傳初始化（預簽網址或直傳）

`POST /v1/attachments`

```json
{ "project_id":"proj_...", "filename":"plan.pdf", "mime":"application/pdf", "modality":"pdf" }
```

**201** → `{ "id":"att_...", "upload": {"url":"...","headers":{}} }`

> 成功上傳後，呼叫 **2.2** 觸發處理。

### 2.2 觸發處理（OCR/ASR/YOLO/切塊/嵌入）

`POST /v1/attachments/:id/ingest`

```json
{ "steps": ["pdf_text", "chunk", "embed"], "priority": "normal" }
```

**202** → `{ "job_id":"job_ingest_...", "status":"queued" }`

### 2.3 查詢處理狀態

`GET /v1/attachments/:id/status` → `{"state":"completed","stages":[...]}`

### 2.4 檢索衍生單位

* `GET /v1/attachments/:id/chunks?limit=50&after=...`
* `GET /v1/attachments/:id/detections?label=helmet`（YOLO）

---

## 3. RAG（多模態）

### 3.1 純檢索（文字為主，含影像關聯）

`POST /v1/rag/search`

```json
{
  "project_id":"proj_...",
  "query":"工地安全帽使用規範",
  "top_k": 8,
  "filters": {"attachment_ids":["att_..."]},
  "include": {"text": true, "image": true}
}
```

**200** →

```json
{
  "hits": [
    {"type":"text","score":0.82,"chunk_id":"chunk_...","attachment_id":"att_...","text":"...","meta":{"page":5}},
    {"type":"image","score":0.74,"det_id":"det_...","attachment_id":"att_...","label":"helmet","bbox":[x,y,w,h],"frame_ts":12.4}
  ]
}
```

### 3.2 具根據生成（Grounded Generation, 可串流）

`POST /v1/rag/generate`（`stream=true` 時回 NDJSON）

```json
{
  "project_id":"proj_...",
  "identity":"agent_esg",
  "query":"用三點說明安全帽規範，每點 20 字。",
  "top_k":6,
  "cite": true,
  "stream": true
}
```

**NDJSON 範例**：

```json
{"event":"search","data":{"took_ms":120,"hits":6}}
{"event":"draft","data":{"text":"1. 施工現場必須..."}}
{"event":"cite","data":{"chunk_id":"chunk_...","attachment_id":"att_...","page":5}}
{"event":"final","data":{"text":"...三點結論..."}}
{"event":"done"}
```

---

## 4. Agents（多 Agent：多選一 / 同步&非同步）

### 4.1 Registry（列出可用 Agent）

`GET /v1/agents`
→ `[{"name":"report_writer","skills":["rag","report"],"modalities":["text","image"],"cost":"medium","latency":"medium"}]`

### 4.2 路由（多選一，僅挑 winner）

`POST /v1/route`

```json
{
  "project_id":"proj_...",
  "intent":"撰寫 ESG 報告的『安全與健康』段落",
  "constraints":{"deadline_s":5,"budget_tokens":4000}
}
```

**200** → `{ "chosen":"report_writer", "candidates":[{"name":"report_writer","score":0.82}], "reason":"需要 RAG+寫作" }`

### 4.3 同步執行（串流事件）

`POST /v1/agents/:name/run?stream=true`

```json
{
  "project_id":"proj_...",
  "identity":"agent_esg",
  "input": {"section_key":"ohs","requirements":["20-30 字/點","附引用"]}
}
```

**NDJSON**：

```json
{"event":"route","data":{"chosen":"report_writer"}}
{"event":"plan","data":{"steps":["rag.search","compose","write_section"]}}
{"event":"step-start","data":{"tool":"rag.search"}}
{"event":"step-end","data":{"took_ms":95,"hits":6}}
{"event":"output","data":{"partial":"1. ..."}}
{"event":"done","data":{"run_id":"run_..."}}
```

### 4.4 背景任務（長作業）

`POST /v1/jobs`

````json
{"type":"agent_run","payload":{...}}```
→ `{ "job_id":"job_...","status":"queued" }`

`GET /v1/jobs/:id` → `{ "status":"running","progress":0.42 }`  
`GET /v1/jobs/:id/events`（SSE/NDJSON）

---

## 5. Reports（模板化報告 / 逐段生成）

### 5.1 建立報告
`POST /v1/reports`
```json
{
  "project_id":"proj_...",
  "type":"esg_v1",
  "schema_version":"1.0",
  "title":"2025 ESG 報告",
  "status":"draft"
}
````

**201** → `{ "id":"rpt_..." }`

### 5.2 段落 CRUD（含引用）

`POST /v1/reports/:id/sections`

```json
{
  "section_key":"ohs",
  "content":{"md":"..."},
  "citations":[
    {"type":"text","chunk_id":"chunk_...","attachment_id":"att_...","page":5},
    {"type":"image","det_id":"det_...","attachment_id":"att_...","bbox":[x,y,w,h],"frame_ts":12.4}
  ]
}
```

`PATCH /v1/reports/:id/sections/:sec_id`（更新內容/狀態）

### 5.3 匯出

`GET /v1/reports/:id/export?format=pdf|html` → 檔案或匯出任務 `job_id`

---

## 6. Policy（黑名單 / 守門）

* `GET /v1/policy` → 當前設定摘要
* `POST /v1/policy/test` → `{ "text":"..." }` → `{ "hit":true,"category":"SRC" }`
* `POST /v1/policy/reload` → 重新載入
* `GET /v1/policy/events?project_id=...` → 命中記錄列表（僅摘要/雜湊，不落地敏感原文）

> 串流回應可能含政策欄位：`{"event":"policy","data":{"blocked":"SRC","triggered":"pre|stream"}}`

---

## 7. Observability（可觀測性 / 稽核）

* `GET /v1/runs?project_id=...`  → 列出代理執行
* `GET /v1/runs/:id` → 模型、token、成本、輸入輸出摘要
* `GET /v1/runs/:id/steps` → 每步工具、耗時、結果摘要
* 指標：延遲、拒答率、RAG 命中、引用覆蓋率、成本

---

## 8. Providers（模型供應商與升級策略）

* 所有可生成/規劃的端點接受：

```json
{
  "provider": {"name":"ollama","model":"qwen2.5:7b-instruct"},
  "upgrade_policy": {"on_low_confidence":true,"fallback":"openai:gpt-4o-mini"}
}
```

* 伺服器端可根據門檻（信心、schema 驗證、步數）自動升級並在回應事件中標示：

```json
{"event":"provider","data":{"chosen":"ollama:qwen2.5-7b","upgraded_to":"openai:gpt-4o-mini"}}
```

---

## 9. NDJSON 事件規範（統一格式）

每行一個 JSON：

```json
{
  "event": "<search|draft|cite|route|plan|step-start|step-end|output|final|policy|provider|error|done>",
  "data":  { ... },
  "req_id": "req_..."  
}
```

**收尾必有**：`{"event":"done"}`

---

## 10. CORS 與 Proxy

* 伺服器掛 `CORSMiddleware`，白名單你的前端（如 `https://eva.4impact.cc`）
* Nginx 反代：`proxy_buffering off;`、不要攔 `OPTIONS`；串流請維持 `chunked_transfer_encoding on;`

---

## 11. 實作里程碑（勾選式）

* [ ] `/v1/projects` / `/v1/identities`（MVP）
* [ ] `/v1/attachments`（上傳→觸發→狀態）
* [ ] `/v1/rag/search`（文字）
* [ ] `/v1/rag/generate`（NDJSON，含 `search/draft/cite/final/done`）
* [ ] `/v1/agents` + `/v1/route`（多選一）
* [ ] `/v1/agents/:name/run?stream=true`（事件：`route/plan/step*/output/done`）
* [ ] `/v1/reports` + `sections` + `citations`
* [ ] Policy `/v1/policy/*`（沿用現有，增事件列表）
* [ ] Observability `/v1/runs*` `/v1/jobs*`
* [ ] Providers 升級策略（回應事件標示）

---

## 12. 附錄：欄位摘要（精簡）

### 12.1 Citation（報告引用）

```json
{
  "type": "text|image",
  "attachment_id": "att_...",
  "chunk_id": "chunk_...",        
  "det_id": "det_...",            
  "page": 5,
  "bbox": [x, y, w, h],
  "frame_ts": 12.4
}
```

### 12.2 Run / Step

```json
{
  "run": {"id":"run_...","project_id":"proj_...","agent":"report_writer","model":"qwen2.5:7b","tokens": {"in":1200,"out":800},"cost":0.002},
  "step": {"idx":1,"tool":"rag.search","args_fingerprint":"sha256:...","took_ms":95,"result_digest":"sha256:..."}
}
```

> 本規格為草案；實作時可先落地 MVP 勾選清單，再逐步擴充。

