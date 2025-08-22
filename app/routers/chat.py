# app/routers/chat.py
import json, asyncio, re, datetime, os
import aiohttp
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse
from app.session_utils import append_history
from app.services.state_store import read_state, write_state
from app.services.parsed_reader import extract_plaintext
from app.services.field_prompts import prompt_name, prompt_philosophy, prompt_sdg
from app.core.ndjson import ndjson_line, one_shot_ndjson
from app.core.regexes import YES_RE, NO_RE, UPLOAD_RE
from app.services.json_parse import parse_json_loose, extract_first_json
from app.services.upstream_client import ask_upstream_json
from app.services.cms_uploader import post_cms_upload
from collections import defaultdict
from app.services.payload_rules import validate_and_fix_payload, need_repair
from app.services.fallback_heuristics import fallback_from_plaintext, fallback_from_parsed_clip
from app.flows.doc_flow import (
    handle_doc_parsed_entry, handle_awaiting_confirm,
    prepare_aligning, prompt_aligned_tip, handle_upload
)
from app.flows.fields_flow import step_f_name, step_f_philosophy, step_f_sdg
from app.core.regexes import YES_RE, UPLOAD_RE
from app.core.streaming import proxy_streaming

router = APIRouter(prefix="/api", tags=["chat"])

def _get_last_user_text(messages):
    for msg in reversed(messages or []):
        if (msg or {}).get("role") == "user":
            return msg.get("content") or ""
    return ""

async def _fake_stream_from_full(payload_bytes: bytes, base_url: str):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90)) as session:
        async with session.post(
            f"{base_url}/api/chat",
            data=payload_bytes,
            headers={"Content-Type": "application/json","Accept-Encoding": "identity"},
        ) as response:
            text = await response.text()

    try:
        data = json.loads(text)
        full = (data.get("message") or {}).get("content") or data.get("response") or text
    except Exception:
        full = text

    async def gen():
        for i in range(0, len(full), 48):
            yield ndjson_line({"message": {"content": full[i:i+48]}, "done": False})
            await asyncio.sleep(0.02)
        yield ndjson_line({"done": True})

    return gen

@router.post("/chat")
async def proxy_ollama_chat(request: Request):
    settings = request.app.state.settings
    base_url   = settings.ollama_base_url
    sess_base  = settings.sess_base
    deny_enabled = settings.deny_enabled

    payload_bytes = await request.body()
    # 解析請求
    try:
        body = json.loads(payload_bytes.decode("utf-8"))
        want_stream = bool(body.get("stream", True))
        messages = body.get("messages") or []
    except Exception:
        want_stream, messages = True, []

    # 讀取共享設定
    base_url     = request.app.state.ollama_base_url
    sess_base    = request.app.state.sess_base
    deny_guard   = getattr(request.app.state, "deny_guard", None)
    deny_enabled = bool(getattr(request.app.state, "deny_enabled", False))

    # 會話模式
    session_id = request.query_params.get("session_id")
    session_mode = bool(session_id)

    # 寫入 user/system 歷史
    if session_mode:
        for m in messages:
            role = (m or {}).get("role")
            if role in ("user", "system"):
                append_history(session_id, role, (m.get("content") or ""), sess_base)

    refusal_text = (deny_guard.refusal_text if deny_guard else "抱歉，我無法回覆這個問題。")

    # 事前政策過濾
    hit_cat = None
    if deny_enabled and deny_guard:
        hit, hit_cat, _ = deny_guard.test_text(_get_last_user_text(messages))
        if hit:
            headers = {
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "X-Policy-Blocked": hit_cat or "1",
                "X-Policy-Triggered": "pre",
                "X-Session-Mode": "session" if session_mode else "stateless",
            }
            if want_stream:
                async def gen_refuse():
                    if session_mode:
                        append_history(session_id, "assistant", refusal_text, sess_base)
                    yield ndjson_line({"message": {"role": "assistant","content": refusal_text}, "done": False})
                    yield ndjson_line({"done": True})
                return StreamingResponse(gen_refuse(), media_type="application/x-ndjson", headers=headers)
            else:
                if session_mode:
                    append_history(session_id, "assistant", refusal_text, sess_base)
                return JSONResponse(
                    {"model": body.get("model"), "message": {"role": "assistant","content": refusal_text}, "done": True},
                    headers=headers,
                )

    # ===== 本地前置：對 conversation_state 做引導/分支 =====
    if session_mode:
        try:
            st = read_state(sess_base, session_id)
        except Exception:
            st = {}

        # === A) 剛 parsed 完
        if session_mode and st.get("mode") == "doc_aligned" and st.get("step") == "parsed" and st.get("doc"):
            text, st = handle_doc_parsed_entry(st)
            write_state(sess_base, session_id, st)
            append_history(session_id, "assistant", text, sess_base)
            return (StreamingResponse(one_shot_ndjson(text)(), media_type="application/x-ndjson",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no","X-Session-Mode":"session"})
                    if want_stream else JSONResponse({"model": body.get("model"),"message":{"role":"assistant","content":text},"done":True},
                    headers={"X-Session-Mode":"session"}))

        # === B) awaiting_confirm
        if session_mode and st.get("mode") == "doc_aligned" and st.get("step") == "awaiting_confirm":
            user_text = _get_last_user_text(messages) or ""
            text, st = handle_awaiting_confirm(st, user_text)
            write_state(sess_base, session_id, st)
            append_history(session_id, "assistant", text, sess_base)
            return (StreamingResponse(one_shot_ndjson(text)(), media_type="application/x-ndjson",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no","X-Session-Mode":"session"})
                    if want_stream else JSONResponse({"model": body.get("model"),"message":{"role":"assistant","content":text},"done":True},
                    headers={"X-Session-Mode":"session"}))

        # === C0) 進入 aligning（由 awaiting_confirm: YES 之後）
        if session_mode and st.get("step") == "aligning":
            text, st = prepare_aligning(st, sess_base, session_id)
            write_state(sess_base, session_id, st)
            append_history(session_id, "assistant", text, sess_base)
            return (StreamingResponse(one_shot_ndjson(text)(), media_type="application/x-ndjson",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no","X-Session-Mode":"session"})
                    if want_stream else JSONResponse({"model": body.get("model"),"message":{"role":"assistant","content":text},"done":True},
                    headers={"X-Session-Mode":"session"}))

        # === C1) f_name
        if session_mode and st.get("step") == "f_name":
            text, st = await step_f_name(st, body.get("model"), base_url, timeout_s)
            write_state(sess_base, session_id, st)
            append_history(session_id, "assistant", text, sess_base)
            return (StreamingResponse(one_shot_ndjson(text)(), media_type="application/x-ndjson",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no","X-Session-Mode":"session"})
                    if want_stream else JSONResponse({...}, headers={"X-Session-Mode":"session"}))

        # === C2) f_philosophy
        if session_mode and st.get("step") == "f_philosophy":
            text, st = await step_f_philosophy(st, body.get("model"), base_url, timeout_s)
            write_state(sess_base, session_id, st)
            append_history(session_id, "assistant", text, sess_base)
            if want_stream:
                return StreamingResponse(one_shot_ndjson(msg)(),
                                        media_type="application/x-ndjson",
                                        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no","X-Session-Mode":"session"})
            else:
                return JSONResponse({"model": body.get("model"),
                                    "message": {"role":"assistant","content": msg},
                                    "done": True},
                                    headers={"X-Session-Mode":"session"})

        # === C3) f_sdg
        if session_mode and st.get("step") == "f_sdg":
            text, st = await step_f_sdg(st, body.get("model"), base_url, timeout_s)
            write_state(sess_base, session_id, st)
            append_history(session_id, "assistant", text, sess_base)
            if want_stream:
                return StreamingResponse(one_shot_ndjson(msg)(),
                                         media_type="application/x-ndjson",
                                         headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no","X-Session-Mode":"session"})
            else:
                return JSONResponse({"model": body.get("model"),
                                     "message": {"role":"assistant","content": msg},
                                     "done": True},
                                    headers={"X-Session-Mode":"session"})


        # === D) aligned：等上傳
        if session_mode and st.get("step") in ("aligned", "aligned_with_warnings"):
            user_text = _get_last_user_text(messages) or ""
            want_upload = bool(UPLOAD_RE.search(user_text) or YES_RE.search(user_text))
            if not want_upload:
                text = prompt_aligned_tip()
                append_history(session_id, "assistant", text, sess_base)
            if want_stream:
                return StreamingResponse(one_shot_ndjson(msg)(),
                                        media_type="application/x-ndjson",
                                        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no","X-Session-Mode":"session"})
            else:
                return JSONResponse({"model": body.get("model"),
                                    "message": {"role":"assistant","content": msg},
                                    "done": True},
                                    headers={"X-Session-Mode":"session"})



    # ===== 本地前置結束：其餘情境照原本邏輯走上游 =====

    # 建立到上游的連線
    timeout = aiohttp.ClientTimeout(total=None, connect=10)
    connector = aiohttp.TCPConnector(force_close=False, enable_cleanup_closed=True)
    session = aiohttp.ClientSession(timeout=timeout, connector=connector)


    try:
        # 非串流
        if not want_stream:
            resp = await session.post(
                f"{base_url}/api/chat",
                data=payload_bytes,
                headers={"Content-Type": "application/json","Accept-Encoding": "identity"},
            )
            txt = await resp.text()
            await resp.release()
            await session.close()

            if session_mode:
                try:
                    data = json.loads(txt)
                    content = ((data.get("message") or {}).get("content")) or data.get("response") or ""
                except Exception:
                    content = ""
                if content:
                    append_history(session_id, "assistant", content, sess_base)

            return JSONResponse(
                content=json.loads(txt) if txt else {},
                headers={"X-Session-Mode": "session" if session_mode else "stateless"},
            )
        # ===== 串流 =====
        return await proxy_streaming(
            request,
            base_url,
            payload_bytes,
            session_mode=session_mode,
            session_id=session_id,
            deny_enabled=deny_enabled,
            deny_guard=deny_guard,
            refusal_text=refusal_text,
            append_history_fn=append_history,
            sess_base=sess_base,
        )
    except RuntimeError as e:
        # 上游回 4xx/5xx 的情況（proxy_streaming raise）
        return JSONResponse(status_code=500, content={"error": str(e)})