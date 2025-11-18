#!/bin/bash

: <<'FLOW'
curl /stream/ai_cat
    ↓
app/routers/streaming.py
    ↓
直接 proxy OLLAMA_GATEWAY_URL

FLOW

curl -N -H "Content-Type: application/json"   -d '{"message":"你是誰"}'   http://localhost:9000/stream/ai_cat