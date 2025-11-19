curl -sN -H "Content-Type: application/json" \
  -d '{
    "role": "ai_cat",
    "input": {
      "model": "openai/gpt-4o-mini",
      "messages": [
        {"role": "system", "content": "所有輸出都用繁體中文（台灣用語）。"},
        {"role": "user", "content": "你的主人的 email 是什麼？"}
      ]
    }
  }' http://localhost:9000/chat
