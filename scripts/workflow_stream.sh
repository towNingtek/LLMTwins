#!/bin/bash

: <<'FLOW'
curl /workflow/ai_cat/stream
    ↓
LangServe add_routes
    ↓
roles/ai_cat/graph.py 的 ai_cat_workflow()
    ↓
workflow node 會呼叫 respond_node()
    ↓
respond_node() 裡呼叫 core/llm_clients.py 的 chat()
    ↓
chat() 使用 httpx.stream() 串流 LLM token

FLOW

curl -sS -N http://localhost:9000/workflow/ai_cat/stream \
  -H "Content-Type: application/json" \
  -d '{"input": {"message": "幫我查今日油價", "mood": ""}}'
