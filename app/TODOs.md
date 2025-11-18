# 【LLMTwins：要實作的功能精華摘要】

## 🎯 目標

打造一個 **通用 Streaming Agent Runtime**，支援：

1. **串流回覆**
2. **偵測 LLM function_call（工具呼叫）**
3. **自動：斷流 → 執行工具 → 再續流**
4. **讓每個角色（role）可插拔自己的工具（含 API key）**
5. **`core/` 不沾黏 `roles/`，保持乾淨可維護**

---

# 🧩 核心設計（最重要）

## 1. Runtime 不認識 role（只負責流程）

Runtime 主要放在 `app/` + `core/`：

* `core/llm_clients.py`：對 `http://localhost:8002/api/chat` 的封裝

  * 支援 **非串流**（一次拿完整 message）
  * 支援 **串流**（async generator token-by-token）

* `app/agent_runtime.py`（新檔）：

  * 實作「**Streaming Agent 通用邏輯**」：

    * 第一次非串流 call → 檢查有沒有 `function_call`
    * 有需要工具 → 執行 tools
    * 第二次改用串流 → 把最後回答 token 一個一個推給前端
  * 透過 `{role}` 字串動態載入 `roles/{role}/...`（prompt / tools / config）

* `app/main.py`：

  * 建立 FastAPI app
  * 掛上通用路由（例如 `/agent/{role}/stream`）

👉 Runtime 不放任何 prompt、不放工具、不放金鑰。

---

## 2. Role 完全自帶：prompt / tools / config

每個角色只維護自己的資料夾，例如：

```bash
roles/{role_name}/
    prompt.py     # persona / system prompt / 回覆語氣
    tools.py      # 該角色專用工具（含 API key、業務邏輯）
    config.json   # 模型名稱、溫度、是否啟用工具等設定
```

* **`prompt.py`**

  * 定義 `SYSTEM_PROMPT` 等字串
* **`tools.py`**

  * 定義 `TOOL_SCHEMAS`（給 LLM 的 function schema）
  * 實作實際的 Python 函式，例如 `async def get_oil_price(...)`
* **`config.json`**

  * 例如：

    ```json
    {
      "model": "openai/gpt-4o-mini",
      "temperature": 0.3,
      "enable_tools": true
    }
    ```

👉 Agent 開發者 **只碰 `roles/{role}/`**，不需要動 `app/`、不需要第二份結構。

---

## 3. 新增通用 API：`POST /agent/{role}/stream`

```http
POST /agent/{role}/stream
Content-Type: application/json

{
  "message": "使用者的問題",
  "session_id": "optional-session-id"
}
```

### 流程（Runtime 負責）：

1. **載入 role 配置**

   * 從 `roles/{role}/prompt.py` 取得 `SYSTEM_PROMPT`
   * 從 `roles/{role}/config.json` 取得 model / 溫度 / 是否啟用工具
   * 從 `roles/{role}/tools.py` 取得 `TOOL_SCHEMAS` 及對應函式

2. **第一次：非串流詢問 LLM**

   * 把 user message + system prompt 丟給 LLM
   * 啟用 `tools` / `tool_choice`，讓 LLM 有機會輸出 `function_call`
   * 根據回傳內容判斷：有沒有要執行工具？

3. **若有 function_call → 執行工具**

   * 解析 `function_call.name` + `arguments`
   * 呼叫 `roles/{role}/tools.py` 中對應的函式
   * 拿到工具結果（JSON / 字串皆可）

4. **第二次：改用串流回答**

   * 建立新的 `messages`：

     * system prompt
     * user message
     * 一則 `tool` role 的訊息（帶入工具結果）
   * 呼叫 `chat(..., stream=True, ...)`
   * 用 `async for` 把 token 一個一個包成 ndjson 回傳給前端：

     * `{"model": "...", "message": {"role": "assistant", "content": "<delta>"}, "done": false}`
   * 最後補一行：`{"done": true}`

👉 前端只要會吃 ndjson，就能「邊跑工具邊看到 LLM 最終回答」。

---

# 🧠 需求對照表

| 需求                               | 是否達成 | 說明                           |
| -------------------------------- | ---- | ---------------------------- |
| 工具不能放 core（會有金鑰）                 | ✔    | 工具放 `roles/{role}/tools.py`  |
| core / app 不該依賴特定 role           | ✔    | 透過 `{role}` 字串動態 import      |
| Streaming Agent 要獨立，不跟角色綁        | ✔    | `/agent/{role}/stream` 為通用管線 |
| 支援 function_call → 斷流 → 工具 → 再續流 | ✔    | `agent_runtime` 負責整套流程       |
| 支援多角色、多工具                        | ✔    | 新增一個 `roles/{role}/` 即可      |

---
