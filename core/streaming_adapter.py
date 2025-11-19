# core/streaming_adapter.py

import json
from typing import Any, AsyncGenerator

from core.llm_clients import (
    stream_openai,
    stream_ollama,
)


# ----------------------------------------------------------
# parse NDJSON line-by-line
# ----------------------------------------------------------
async def parse_gateway_stream(llm_stream):
    async for line in llm_stream:
        if not line:
            continue
        try:
            obj = json.loads(line)
        except:
            continue
        yield obj


# ----------------------------------------------------------
# MAIN RUNTIME
# ----------------------------------------------------------
async def unified_stream(
    model: str,
    messages: list,
    tools: list,
    tool_executor,
) -> AsyncGenerator[str, None]:
    """
    統一 Streaming Runtime：
    - 呼叫 /api/chat（OpenAI 風格 NDJSON）
    - 支援 tools（function_call）
    - 自動續流
    """

    # ------------------------------------------------------
    # 內部：呼叫 LLM（注意：不要塞多的參數）
    # ------------------------------------------------------
    async def call_llm(msgs):
        # openai 系列 → 用 stream_openai
        if model.startswith("openai/"):
            return stream_openai(
                model=model,
                messages=msgs,
                tools=tools,
            )

        # 其他一律視為 Ollama Gateway
        return stream_ollama(
            messages=msgs,
            model=model,
            tools=tools,
        )

    # ------------------------------------------------------
    # ROUND 1
    # ------------------------------------------------------
    llm_stream = await call_llm(messages)

    async for obj in parse_gateway_stream(llm_stream):
        # 一般文字 token
        if "message" in obj:
            yield json.dumps({
                "type": "message",
                "content": obj["message"]["content"],
            }, ensure_ascii=False) + "\n"

        # 沒有工具，直接結束
        if obj.get("done"):
            yield json.dumps({"type": "done"}) + "\n"
            return

        # ✅ 工具呼叫（注意：這裡用 tool_calls，OpenAI 風格是複數）
        if "tool_calls" in obj:
            for tc in obj["tool_calls"]:
                name = tc["function"]["name"]
                raw_args = tc["function"].get("arguments") or "{}"

                try:
                    args_dict = json.loads(raw_args)
                except:
                    args_dict = {}

                # 先把工具呼叫事件丟回前端（debug 用）
                yield json.dumps({
                    "type": "tool_call",
                    "content": tc,
                }, ensure_ascii=False) + "\n"

                # === 執行 tools ===
                tool_result = await tool_executor(name, args_dict)

                # ★★★★★ 必修正：生成合法 tool_call_id（V2 必要）
                tc_id = tc.get("id") or f"call_{name}"

                # ★★★★★ assistant 回傳 tool_calls（複數）＋ content=None
                messages.append({
                    "role": "assistant",
                    "tool_calls": [{
                        "id": tc_id,
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": raw_args,
                        }
                    }],
                    "content": None,
                })

                # ★★★★★ tool 回覆必須加 tool_call_id（V2 必要）
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": json.dumps(tool_result, ensure_ascii=False),
                })

            # --------------------------------------------------
            # ROUND 2：帶 tool 結果續流
            # --------------------------------------------------
            llm_stream2 = await call_llm(messages)

            async for obj2 in parse_gateway_stream(llm_stream2):

                if "message" in obj2:
                    yield json.dumps({
                        "type": "message",
                        "content": obj2["message"]["content"],
                    }, ensure_ascii=False) + "\n"

                if obj2.get("done"):
                    yield json.dumps({"type": "done"}) + "\n"
                    return


    # 萬一 LLM 沒送 done，就自己收尾
    yield json.dumps({"type": "done"}) + "\n"
