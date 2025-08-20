# app/routers/chat.py
import json, asyncio
import aiohttp
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse
from app.session_utils import append_history

router = APIRouter(prefix="/api", tags=["chat"])

def ndjson_line(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")

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

        # 串流
        resp = await session.post(
            f"{base_url}/api/chat",
            data=payload_bytes,
            headers={"Content-Type": "application/json","Accept-Encoding": "identity"},
            allow_redirects=False,
        )

        if resp.status >= 400:
            err = await resp.read()
            await resp.release()
            await session.close()
            return JSONResponse(status_code=resp.status, content={"error": err.decode("utf-8","ignore")})

        async def gen():
            got_any = False
            linebuf = ""
            assistant_buffer = []
            try:
                async for chunk in resp.content.iter_chunked(8192):
                    got_any = True
                    if await request.is_disconnected():
                        break
                    if not chunk:
                        continue
                    piece = chunk.decode("utf-8", "ignore")
                    linebuf += piece

                    while True:
                        i = linebuf.find("\n")
                        if i < 0: break
                        line = linebuf[:i]; linebuf = linebuf[i+1:]
                        ls = line.strip()

                        # 串流中政策過濾
                        if deny_enabled and deny_guard and ls.startswith("{"):
                            try:
                                obj = json.loads(ls)
                                content = ((obj.get("message") or {}).get("content")) or ""
                                if content and session_mode: assistant_buffer.append(content)
                                hit, _, _ = deny_guard.test_text(content or "")
                                if hit:
                                    try: await resp.release()
                                    except: pass
                                    try: await session.close()
                                    except: pass
                                    if session_mode:
                                        append_history(session_id, "assistant", refusal_text, sess_base)
                                    yield ndjson_line({"message":{"role":"assistant","content":refusal_text},"done":False})
                                    yield ndjson_line({"done": True})
                                    return
                            except Exception:
                                pass
                        else:
                            try:
                                obj = json.loads(ls)
                                content = ((obj.get("message") or {}).get("content")) or ""
                                if content and session_mode: assistant_buffer.append(content)
                            except Exception:
                                pass

                        yield (line + "\n").encode("utf-8")
                        await asyncio.sleep(0)

                if linebuf:
                    ls = linebuf.strip()
                    if deny_enabled and deny_guard and ls.startswith("{"):
                        try:
                            obj = json.loads(ls)
                            content = ((obj.get("message") or {}).get("content")) or ""
                            if content and session_mode: assistant_buffer.append(content)
                            hit, _, _ = deny_guard.test_text(content or "")
                            if hit:
                                try: await resp.release()
                                except: pass
                                try: await session.close()
                                except: pass
                                if session_mode:
                                    append_history(session_id, "assistant", refusal_text, sess_base)
                                yield ndjson_line({"message":{"role":"assistant","content":refusal_text},"done":False})
                                yield ndjson_line({"done": True})
                                return
                        except Exception:
                            pass
                    yield (linebuf + ("\n" if not linebuf.endswith("\n") else "")).encode("utf-8")

            except Exception as e:
                if not got_any:
                    try: await resp.release()
                    except: pass
                    try: await session.close()
                    except: pass
                    fake = await _fake_stream_from_full(payload_bytes, base_url)
                    async for c in fake():
                        try:
                            obj = json.loads(c.decode("utf-8"))
                            content = ((obj.get("message") or {}).get("content")) or ""
                            if content and session_mode: assistant_buffer.append(content)
                        except Exception:
                            pass
                        yield c
                else:
                    yield b'{"done": true}\n'
            finally:
                if session_mode and assistant_buffer:
                    try:
                        append_history(session_id, "assistant", "".join(assistant_buffer), sess_base)
                    except Exception:
                        pass
                try: await resp.release()
                except: pass
                try: await session.close()
                except: pass

        headers = {"Cache-Control": "no-cache","X-Accel-Buffering": "no","X-Session-Mode": "session" if session_mode else "stateless"}
        if hit_cat:
            headers["X-Policy-Blocked"] = hit_cat
            headers["X-Policy-Triggered"] = "pre"

        return StreamingResponse(gen(), media_type=resp.headers.get("Content-Type", "application/x-ndjson"), headers=headers)

    except Exception:
        try: await session.close()
        except: pass
        fake = await _fake_stream_from_full(payload_bytes, base_url)
        return StreamingResponse(fake(), media_type="application/x-ndjson",
                                 headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no",
                                          "X-Session-Mode":"session" if session_mode else "stateless"})
