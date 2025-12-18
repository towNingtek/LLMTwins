# openai/gpt-4o-mini
# llama3:instruct
SYS='所有輸出一律正體中文（台灣用語），禁止任何英文字母與拼音。只輸出答案，不要解釋。'

EXAMPLE='您好，歡迎光臨！請問需要哪方面的協助？
感謝您的來電，請問我可以如何協助您？
很高興為您服務，若有問題隨時告訴我。'

curl -sS -N --http1.1 --no-buffer http://localhost:8082/api/chat \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc --arg sys "$SYS" --arg ex "$EXAMPLE" '{
    model:"openai/gpt-4o-mini",
    stream:true,
    options:{temperature:0.2},
    messages:[
      {role:"system",content:$sys},
      {role:"assistant",content:$ex},
      {role:"user",content:"再產出三句不同的客服問候語，維持同樣語氣與長度。"}
    ]
  }')"

