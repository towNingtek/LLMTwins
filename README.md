# 📘 LLMTwins — Multi‑Role Workflow Server

LLMTwins 是一套基於 **FastAPI + LangGraph + LangServe**、並支援「多角色自動載入」的工作流程系統。

每個角色（role）是一個獨立的 AI agent workflow，包含：

```
roles/<role>/
  ├─ state.py        # workflow 狀態定義
  ├─ nodes/          # 每個行為節點
  └─ graph.py        # workflow 組裝（StateGraph）
```

新增角色時 **不需修改 main.py、不需新增 router、不需 import**，LLMTwins 會自動掃描 roles 目錄、載入 workflow 並產生 API endpoints。

---

# 🚀 系統架構

**FastAPI**

* Hosting API server
* 提供 `/workflow/<role>/...` 端點

**LangGraph**

* 建構每個角色的 State Machine
* 每個角色是獨立流程（StateGraph）

**LangServe**

* 自動將 Workflow 轉成 REST API
* 自動產生：

  * `/invoke`（非串流）
  * `/stream`（SSE 串流）
  * `/batch`（批次）

**LLMTwins Dynamic Role Loader**

* 自動掃描 `roles/` 資料夾
* 動態 import `<role>/graph.py`
* 呼叫 `<role>_workflow()` 回傳 workflow instance
* 自動掛載到： `/workflow/<role>`

---

# 🐣 如何新增一個角色（範例：AI 小雞）

以下示範新增 `ai_chicken` 角色。

---

## ✅ Step 1 — 建立資料夾

```
roles/
  ai_chicken/
```

---

## ✅ Step 2 — 建立 state.py

每個 workflow 必須定義 state（TypedDict）：

```python
# roles/ai_chicken/state.py
from typing import TypedDict

class ChickenState(TypedDict):
    message: str
    mood: str
```

---

## ✅ Step 3 — 建立 nodes/respond.py

```python
# roles/ai_chicken/nodes/respond.py
from core.llm_clients import chat

async def respond_node(state):
    user_msg = state["message"]

    # 使用 LLMTwins 的封裝 chat() 呼叫 LLM
    res = await chat(
        model="openai/gpt-4o-mini",
        stream=False,
        messages=[
            {"role": "system", "content": "你是一隻可愛的小雞，語氣啾啾的"},
            {"role": "user", "content": user_msg},
        ],
    )

    reply = res.get("content", "")

    return {
        "message": reply,
        "mood": "chirpy",
    }
```

✔ node 回傳的是 **部分 state 更新（dict）**

---

## ✅ Step 4 — 建立 graph.py

```python
# roles/ai_chicken/graph.py
from langgraph.graph import StateGraph, END
from .state import ChickenState
from .nodes.respond import respond_node

def ai_chicken_workflow():
    builder = StateGraph(ChickenState)

    builder.add_node("respond", respond_node)
    builder.set_entry_point("respond")
    builder.add_edge("respond", END)

    return builder.compile()
```

✔ workflow 必須以 `def <role>_workflow():` 命名
✔ main.py 會自動以此命名規則載入

---

## ✅ Step 5 — 自動可用！無需修改 main.py

LangServe 會自動建立 API endpoints：

### ▶ 非串流 Invoke

```
POST /workflow/ai_chicken/invoke
{
  "input": {
    "message": "哈囉",
    "mood": ""
  }
}
```

### ▶ 串流（SSE）

```
POST /workflow/ai_chicken/stream
```

返回格式：

```
event: metadata
event: data
event: end
```

### ▶ Bash 測試範例

```bash
curl -sS -N http://localhost:9000/workflow/ai_chicken/stream \
  -H "Content-Type: application/json" \
  -d '{"input": {"message": "你是誰？", "mood": ""}}'
```

---

# 🌈 已支援的兩大能力

## ✔ 1. **純聊天（直接串流）**

路徑：

```
POST /stream/<role>
```

用途：

* 走 LLM 直接輸出
* 模仿 simple chat API（Ollama/OpenAI 風格）

## ✔ 2. **LangGraph workflow（可串流）**

路徑：

```
POST /workflow/<role>/stream
POST /workflow/<role>/invoke
```

用途：

* 多步驟 AI agent
* 支援 tools、RAG、ontology、API call、db 查詢等

---

# 📂 專案結構（重點）

```
LLMTwins/
├─ app/
│   ├─ main.py           # FastAPI + Dynamic Loader
│   └─ routers/
│       └─ streaming.py  # 基本聊天串流 API
├─ core/
│   └─ llm_clients.py    # LLM chat wrapper (stream + non-stream)
└─ roles/
    ├─ ai_cat/
    ├─ ai_chicken/
    └─ ...
```

---

# 🔧 Dynamic Role Loading（dynamic import）

main.py 自動掃描：

```
roles/*/graph.py
```

並尋找：

```
<role>_workflow()
```

找到後自動掛載為：

```
/workflow/<role>/invoke
/workflow/<role>/stream
/workflow/<role>/batch
```

無需任何額外程式碼。

---