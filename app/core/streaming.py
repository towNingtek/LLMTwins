# app/core/streaming.py
import json, aiohttp, asyncio
from typing import AsyncGenerator, Optional, List
from fastapi import Request
from fastapi.responses import StreamingResponse
from app.core.ndjson import ndjson_line

async def proxy_streaming(
    request: Request,
    base_url: str,
    payload_bytes: bytes,
    *,
    session_mode: bool,
    session_id: Optional[str],
    deny_enabled: bool,
    deny_guard,  # 可為 None；需具備 .test_text(text)->(hit, cat, extra)
    refusal_text: str,
    append_history_fn,  # 介面：append_history(session_id, role, text, sess_base)
    sess_base,
) -> StreamingResponse:
    """
    將 /api/chat 的串流請求轉發至上游，維持原有：
    - 逐行 NDJSON 代理
    - 串流中逐行政策檢查（命中→立即中止並回拒絕文）
    - 斷線或例外→降級為『假串流』一次性回傳
    - 會話模式下，彙整 assistant 內容落盤
    """
    timeout = aiohttp.ClientTimeout(total=None, connect=10)
    connector = aiohttp.TCPConnector(force_close=False, enable_cleanup_closed=True)
    session = aiohttp.ClientSession(timeout=timeout, connector=connector)

    async def _fake_stream_from_full() -> AsyncGenerator[bytes, None]:
        # 回退：非串流請求一次取回，再切片丟 NDJSON
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90)) as s:
            async with s.post(
                f"{base_url}/api/chat",
                data=payload_bytes,
                headers={"Content-Type":"application/json","Accept-Encoding":"identity"},
            ) as r:
                text = await r.text()
        try:
            data = json.loads(text)
            full = (data.get("message") or {}).get("content") or data.get("response") or text
        except Exception:
            full = text
        for i in range(0, len(full), 48):
            yield ndjson_line({"message":{"content": full[i:i+48]}, "done": False})
            await asyncio.sleep(0.02)
        yield ndjson_line({"done": True})

    try:
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
            # 直接把錯誤往外丟，由呼叫端決定回 JSONResponse
            raise RuntimeError(err.decode("utf-8", "ignore"))

        async def gen():
            got_any = False
            linebuf = ""
            assistant_buffer: List[str] = []

            try:
                async for chunk in resp.content.iter_chunked(8192):
                    got_any = True
                    if await request.is_disconnected():
                        break
                    if not chunk:
                        continue

                    piece = chunk.decode("utf-8","ignore")
                    linebuf += piece

                    while True:
                        i = linebuf.find("\n")
                        if i < 0:
                            break
                        line = linebuf[:i]; linebuf = linebuf[i+1:]
                        ls = line.strip()

                        # 逐行解析、政策檢查（若有開啟）
                        if deny_enabled and deny_guard and ls.startswith("{"):
                            try:
                                obj = json.loads(ls)
                                content = ((obj.get("message") or {}).get("content")) or ""
                                if content and session_mode:
                                    assistant_buffer.append(content)
                                hit, _, _ = deny_guard.test_text(content or "")
                                if hit:
                                    try: await resp.release()
                                    except: pass
                                    try: await session.close()
                                    except: pass
                                    if session_mode and session_id and assistant_buffer:
                                        append_history_fn(session_id, "assistant", "".join(assistant_buffer), sess_base)
                                    yield ndjson_line({"message":{"role":"assistant","content":refusal_text},"done":False})
                                    yield ndjson_line({"done": True})
                                    return
                            except Exception:
                                pass
                        else:
                            # 一般彙整（無政策或非 JSON 行）
                            try:
                                obj = json.loads(ls)
                                content = ((obj.get("message") or {}).get("content")) or ""
                                if content and session_mode:
                                    assistant_buffer.append(content)
                            except Exception:
                                pass

                        yield (line + "\n").encode("utf-8")
                        await asyncio.sleep(0)

                # 收尾：處理殘餘緩衝
                if linebuf:
                    ls = linebuf.strip()
                    if deny_enabled and deny_guard and ls.startswith("{"):
                        try:
                            obj = json.loads(ls)
                            content = ((obj.get("message") or {}).get("content")) or ""
                            if content and session_mode:
                                assistant_buffer.append(content)
                            hit, _, _ = deny_guard.test_text(content or "")
                            if hit:
                                try: await resp.release()
                                except: pass
                                try: await session.close()
                                except: pass
                                if session_mode and session_id and assistant_buffer:
                                    append_history_fn(session_id, "assistant", "".join(assistant_buffer), sess_base)
                                yield ndjson_line({"message":{"role":"assistant","content":refusal_text},"done":False})
                                yield ndjson_line({"done": True})
                                return
                        except Exception:
                            pass
                    yield (linebuf + ("\n" if not linebuf.endswith("\n") else "")).encode("utf-8")

            except Exception:
                # 未收到任何資料 → 直接走假串流降級
                if not got_any:
                    async for c in _fake_stream_from_full():
                        try:
                            obj = json.loads(c.decode("utf-8"))
                            content = ((obj.get("message") or {}).get("content")) or ""
                            if content and session_mode:
                                assistant_buffer.append(content)
                        except Exception:
                            pass
                        yield c
                else:
                    yield b'{"done": true}\n'
            finally:
                if session_mode and session_id:
                    try:
                        # 將累計內容寫入歷史
                        if assistant_buffer:
                            append_history_fn(session_id, "assistant", "".join(assistant_buffer), sess_base)
                    except Exception:
                        pass
                try: await resp.release()
                except: pass
                try: await session.close()
                except: pass

        headers = {"Cache-Control":"no-cache","X-Accel-Buffering":"no"}
        if session_mode:
            headers["X-Session-Mode"] = "session"
        else:
            headers["X-Session-Mode"] = "stateless"
        return StreamingResponse(gen(), media_type=resp.headers.get("Content-Type","application/x-ndjson"), headers=headers)

    except Exception:
        # 外層錯誤 → 直接使用假串流降級
        async def fallback_gen():
            async for c in _fake_stream_from_full():
                yield c
        headers = {"Cache-Control":"no-cache","X-Accel-Buffering":"no","X-Session-Mode":"session" if session_mode else "stateless"}
        return StreamingResponse(fallback_gen(), media_type="application/x-ndjson", headers=headers)
