# app/routers/chat.py
import json, asyncio, re, datetime, os
import aiohttp
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse
from app.session_utils import append_history
from app.services.state_store import read_state, write_state
from app.services.parsed_reader import extract_plaintext
from app.services.field_prompts import prompt_name, prompt_philosophy, prompt_sdg
from app.services.demo_mode import in_demo_mode, pick_demo_payload, fake_upload
from app.core.ndjson import ndjson_line, one_shot_ndjson
from app.core.regexes import YES_RE, NO_RE, UPLOAD_RE
from app.services.json_parse import parse_json_loose, extract_first_json
from app.services.upstream_client import ask_upstream_json
from app.services.cms_uploader import post_cms_upload
from collections import defaultdict
from app.services.payload_rules import validate_and_fix_payload, need_repair
from app.services.fallback_heuristics import fallback_from_plaintext, fallback_from_parsed_clip
import re, json

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

        # A) 剛 parsed 完：先回引導訊息，並把 step -> awaiting_confirm
        if st.get("mode") == "doc_aligned" and st.get("step") == "parsed" and st.get("doc"):
            st["step"] = "awaiting_confirm"
            write_state(sess_base, session_id, st)
            doc = st["doc"] or {}
            filename = doc.get("filename", "已上傳文件")
            pages = doc.get("pages", "?")
            guide = (
                f"我注意到你剛上傳了《{filename}》（{pages} 頁）。\n"
                f"要不要我幫你把內容轉成『永續專案』並直接上傳到永續系統？\n"
                f"請回覆：『好』或『先不要』。"
            )

            # 記錄歷史，並本地回一條 NDJSON
            append_history(session_id, "assistant", guide, sess_base)
            if want_stream:
                return StreamingResponse(
                    one_shot_ndjson(guide)(),
                    media_type="application/x-ndjson",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no",
                             "X-Session-Mode":"session"}
                )
            else:
                return JSONResponse(
                    {"model": body.get("model"),
                     "message": {"role":"assistant","content": guide},
                     "done": True},
                    headers={"X-Session-Mode":"session"}
                )

        # B) 等使用者回覆：判斷 好 / 先不要
        if st.get("mode") == "doc_aligned" and st.get("step") == "awaiting_confirm":
            user_text = _get_last_user_text(messages) or ""

            # show debug 
            print("Debug: User response in awaiting_confirm:", user_text)
            if YES_RE.search(user_text):
                # === Demo：秒出完整草稿，並且立刻上傳到 CMS ===
                if in_demo_mode():
                    # 🔥 確保 st 不是 None - 移到最前面
                    if st is None:
                        st = {}
                        print("Warning: session state was None, initialized empty dict")

                    payload = pick_demo_payload()
                    # Show debug
                    print("Debug: Demo mode, using payload:", json.dumps(payload, ensure_ascii=False, indent=2))

                    # 確保 cms 字典存在
                    if "cms" not in st:
                        st["cms"] = {}

                    status_code, data, raw = await post_cms_upload(pending, settings.cms_upload_url)

                    # debug msg
                    print("Debug: CMS upload response:", status_code, data, raw)

                    if 200 <= status_code < 300:
                        uuid = data.get("uuid") or data.get("id") or ""
                        st["step"] = "session_only"
                        print(f"Debug: st after setting step = {type(st)}")

                        # 🔥 直接設定，不用 setdefault
                        st["cms"] = {"uuid": uuid}

                        write_state(sess_base, session_id, st)
                        url = f"https://nsdgs.4impact.cc/content/{uuid}" if uuid else ""
                        msg = (
                            "已自動產生並上傳永續專案。\n"
                            f"專案編號：{uuid or '（未回傳編號）'}" + (f"\n連結：{url}" if uuid else "")
                        )
                    else:
                        # 🔥 在失敗分支也要檢查 st
                        if st is None:
                            st = {}
                            print("Warning: session state was None in failure branch, initialized empty dict")

                        # 上傳失敗就停在 aligned，讓你可以再手動「上傳」
                        st["cms"] = {"pending_payload": payload}  # 直接設定，不用 setdefault
                        st["step"] = "aligned"

                        write_state(sess_base, session_id, st)
                        msg = f"草稿已產生，但上傳失敗 (HTTP {status_code})。\n\n你可回『上傳』再試一次。"
                    append_history(session_id, "assistant", msg, sess_base)
                    if want_stream:
                        return StreamingResponse(one_shot_ndjson(msg)(),
                                                 media_type="application/x-ndjson",
                                                 headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no","X-Session-Mode":"session"})
                    else:
                        return JSONResponse({"model": body.get("model"),
                                             "message": {"role":"assistant","content": msg},
                                             "done": True},
                                            headers={"X-Session-Mode":"session"})
                else:
                    # === 非 Demo 才走原本對話 ===
                    # 🔥 確保 st 不是 None
                    if st is None:
                        st = {}
                        print("Warning: session state was None in non-demo mode, initialized empty dict")

                    st["step"] = "aligning"  # 下一步將 parsed.json -> 參數 -> 送 CMS
                    write_state(sess_base, session_id, st)
                    msg = "收到！等我產出草稿，你回『上傳』我就送到永續系統"

                    append_history(session_id, "assistant", msg, sess_base)
                    if want_stream:
                        return StreamingResponse(
                            one_shot_ndjson(msg)(),
                            media_type="application/x-ndjson",
                            headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no",
                                     "X-Session-Mode":"session"}
                        )
                    else:
                        return JSONResponse(
                            {"model": body.get("model"),
                             "message": {"role":"assistant","content": msg},
                             "done": True},
                            headers={"X-Session-Mode":"session"}
                        )
            elif NO_RE.search(user_text):
                # show debug
                print("Debug!!!: User response in awaiting_confirm is NO branch:", user_text)


                # 🔥 確保 st 不是 None
                if st is None:
                    st = {}
                    print("Warning: session state was None in NO branch, initialized empty dict")

                st["step"] = "session_only"  # 回到 session_only 狀態
                write_state(sess_base, session_id, st)
                msg = "好的，先不轉。如果還有其他需求，請重新上傳文件。"

                append_history(session_id, "assistant", msg, sess_base)
                if want_stream:
                    return StreamingResponse(
                        one_shot_ndjson(msg)(),
                        media_type="application/x-ndjson",
                        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no",
                                 "X-Session-Mode":"session"}
                    )
                else:
                    return JSONResponse(
                        {"model": body.get("model"),
                         "message": {"role":"assistant","content": msg},
                         "done": True},
                        headers={"X-Session-Mode":"session"}
                    )
            else:
                # 既不是「好」也不是「先不要」→ 再提醒一次（不改 step）
                msg = "要不要我幫你把文件轉成永續專案並上傳到永續系統？請回『好』或『先不要』。"
                append_history(session_id, "assistant", msg, sess_base)
                if want_stream:
                    return StreamingResponse(
                        one_shot_ndjson(msg)(),
                        media_type="application/x-ndjson",
                        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no",
                                 "X-Session-Mode":"session"}
                    )
                else:
                    return JSONResponse(
                        {"model": body.get("model"),
                         "message": {"role":"assistant","content": msg},
                         "done": True},
                        headers={"X-Session-Mode":"session"}
                    )
                # === 非 Demo 才走原本對話 ===

                st["step"] = "aligning"  # 下一步將 parsed.json -> 參數 -> 送 CMS
                write_state(sess_base, session_id, st)
                msg = "收到！等我產出草稿，你回『上傳』我就送到永續系統"

                append_history(session_id, "assistant", msg, sess_base)
                if want_stream:
                    return StreamingResponse(
                        one_shot_ndjson(msg)(),
                        media_type="application/x-ndjson",
                        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no",
                                 "X-Session-Mode":"session"}
                    )
                else:
                    return JSONResponse(
                        {"model": body.get("model"),
                         "message": {"role":"assistant","content": msg},
                         "done": True},
                        headers={"X-Session-Mode":"session"}
                    )

            if NO_RE.search(user_text):
                st["step"] = "parsed"  # 回到 parsed 狀態
                write_state(sess_base, session_id, st)
                msg = "好的，先不轉。你隨時可以說『好』，我會幫你處理上傳。"

                append_history(session_id, "assistant", msg, sess_base)
                if want_stream:
                    return StreamingResponse(
                        one_shot_ndjson(msg)(),
                        media_type="application/x-ndjson",
                        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no",
                                 "X-Session-Mode":"session"}
                    )
                else:
                    return JSONResponse(
                        {"model": body.get("model"),
                         "message": {"role":"assistant","content": msg},
                         "done": True},
                        headers={"X-Session-Mode":"session"}
                    )

            # 既不是「好」也不是「先不要」→ 再提醒一次（不改 step）
            msg = "要不要我幫你把文件轉成永續專案並上傳到永續系統？請回『好』或『先不要』。"
            append_history(session_id, "assistant", msg, sess_base)
            if want_stream:
                return StreamingResponse(
                    one_shot_ndjson(msg)(),
                    media_type="application/x-ndjson",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no",
                             "X-Session-Mode":"session"}
                )
            else:
                return JSONResponse(
                    {"model": body.get("model"),
                     "message": {"role":"assistant","content": msg},
                     "done": True},
                    headers={"X-Session-Mode":"session"}
                )

        # C) 進入 aligning：改為逐條流程，先切到 f_name
        if st.get("step") == "aligning":
            try:
                plain = extract_plaintext(sess_base, session_id, max_chars=3000)
            except Exception as e:
                msg = f"讀取 parsed.json 失敗：{e}"
                append_history(session_id, "assistant", msg, sess_base)
                if want_stream:
                    return StreamingResponse(one_shot_ndjson(msg)(),
                                            media_type="application/x-ndjson",
                                            headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no","X-Session-Mode":"session"})
                else:
                    return JSONResponse({"model": body.get("model"),
                                        "message": {"role":"assistant","content": msg},
                                        "done": True},
                                        headers={"X-Session-Mode":"session"})

            if not isinstance(st, dict):
                st = {}
            if not isinstance(st.get("cms"), dict):
                st["cms"] = {}

            st["cms"]["pending_payload"] = {
                "email": "forus999@gmail.com",  # 先放固定值
                "project_start_date": "2025-01-01",
                "project_due_date": "2025-12-31",
                "list_sdg": "0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0",
                "weight_description": {},
                "budget": 0,
                "is_budget_revealed": False,
                "name": "",
                "philosophy": "",
            }
            st["cms"]["plain"] = plain  # 後續每欄都用
            st["step"] = "f_name"
            write_state(sess_base, session_id, st)

            tip = "我先從文件裡抓『計畫名稱』，完成後會給你看草稿，沒問題請回「好」。"
            append_history(session_id, "assistant", tip, sess_base)
            if want_stream:
                return StreamingResponse(one_shot_ndjson(tip)(),
                                        media_type="application/x-ndjson",
                                        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no","X-Session-Mode":"session"})
            else:
                return JSONResponse({"model": body.get("model"),
                                    "message": {"role":"assistant","content": tip},
                                    "done": True},
                                    headers={"X-Session-Mode":"session"})

        # ---- Demo 快速路徑：直接產生草稿，不讀 PDF、不叫上游 ----
        if in_demo_mode() and st.get("step") in ("f_name", "f_philosophy", "f_sdg"):
            st.setdefault("cms", {})["pending_payload"] = pick_demo_payload()
            st["step"] = "aligned"
            write_state(sess_base, session_id, st)
            pretty = json.dumps(st["cms"]["pending_payload"], ensure_ascii=False)
            msg = f"（Demo）目前草稿：\n{pretty}\n\n回『上傳』我就幫你送出（Demo 連結）。"
            append_history(session_id, "assistant", msg, sess_base)
            if want_stream:
                return StreamingResponse(one_shot_ndjson(msg)(),
                                        media_type="application/x-ndjson",
                                        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no","X-Session-Mode":"session"})
            else:
                return JSONResponse({"model": body.get("model"),
                                    "message": {"role":"assistant","content": msg},
                                    "done": True},
                                    headers={"X-Session-Mode":"session"})
        # ---- Demo 路徑結束，以下是原本 C1/C2/C3 正常流程 ----

        # C1) 逐條：抓 name
        if st.get("step") == "f_name":
            plain = (st.get("cms") or {}).get("plain") or ""
            system, user = prompt_name(plain)
            upstream_payload = {
                "model": body.get("model"),
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
            # 原本組 messages OK，改成用共用函式
            print("Debug: Asking upstream for name with payload:", json.dumps(upstream_payload, ensure_ascii=False))
                        # 第一次請求
            ok, txt = await ask_upstream_json(
                base_url, body.get("model"),
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                timeout_s=settings.upstream_timeout_s,
            )

            name_val = ""
            if ok:
                try:
                    data = json.loads(txt)
                    raw = ((data.get("message") or {}).get("content")) or data.get("response") or txt
                    name_obj = json.loads(raw) if raw.strip().startswith("{") else {}
                    name_val = (name_obj.get("name") or "").strip()
                except Exception:
                    name_val = ""

            # 若第一次失敗或結果為空 → 重送一次
            if not name_val:
                print("Debug: name retry once ...")
                ok, txt = await ask_upstream_json(
                    base_url, body.get("model"),
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    timeout_s=settings.upstream_timeout_s,
                )
                if ok:
                    try:
                        data = json.loads(txt)
                        raw = ((data.get("message") or {}).get("content")) or data.get("response") or txt
                        name_obj = json.loads(raw) if raw.strip().startswith("{") else {}
                        name_val = (name_obj.get("name") or "").strip()
                    except Exception:
                        name_val = ""

            if not name_val:
                name_val = "（待補正式名稱）"


            st.setdefault("cms", {}).setdefault("pending_payload", {})["name"] = name_val
            st["step"] = "f_philosophy"
            write_state(sess_base, session_id, st)

            msg = f"暫定計畫名稱：{name_val}\n接著我會產生 120~180 字的『計畫理念』，沒問題請回「好」。"
            append_history(session_id, "assistant", msg, sess_base)
            if want_stream:
                return StreamingResponse(one_shot_ndjson(msg)(),
                                        media_type="application/x-ndjson",
                                        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no","X-Session-Mode":"session"})
            else:
                return JSONResponse({"model": body.get("model"),
                                    "message": {"role":"assistant","content": msg},
                                    "done": True},
                                    headers={"X-Session-Mode":"session"})

        # C2) 逐條：抓 philosophy
        if st.get("step") == "f_philosophy":
            plain = (st.get("cms") or {}).get("plain") or ""
            system, user = prompt_philosophy(plain)
            upstream_payload = {
                "model": body.get("model"),
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
            ok, txt = await ask_upstream_json(base_url, body.get("model"), [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ], timeout_s=settings.upstream_timeout_s,)

            print("Debug: Upstream response for philosophy:", txt)

            if not ok:
                phil = ""  # 先給空字串，等清理與限長後也能跑下去
            else:
                try:
                    data = json.loads(txt)
                    raw = ((data.get("message") or {}).get("content")) or data.get("response") or txt
                    phil_obj = json.loads(raw) if raw.strip().startswith("{") else {}
                    phil = (phil_obj.get("philosophy") or "").strip()
                except Exception:
                    phil = ""

            # 清理與限長（保留你原本這段）
            from html import unescape as _un
            import re as _re
            phil = _un(_re.sub(r"\s+", " ", phil))
            phil = _re.sub(r'\{\s*"page"\s*:\s*\d+[^}]*\}', "", phil)[:180].strip()

            # 若仍為空，可放一個簡短 placeholder，避免前端以為沒完成
            if not phil:
                phil = "本計畫旨在推動在地發展與跨域合作，強化治理能力並提升公共價值。"


            st.setdefault("cms", {}).setdefault("pending_payload", {})["philosophy"] = phil
            # 下一步：先把現在的兩欄草稿給使用者看，等他說「好」再進 SDG（之後再加）
            st["step"] = "f_sdg"
            write_state(sess_base, session_id, st)

            pretty = json.dumps(st["cms"]["pending_payload"], ensure_ascii=False)
            msg = f"目前草稿（名稱＋理念）：\n{pretty}\n\n如果沒問題，可以回『好』；我會開始計算 SDGs 權重。"
            append_history(session_id, "assistant", msg, sess_base)
            if want_stream:
                return StreamingResponse(one_shot_ndjson(msg)(),
                                        media_type="application/x-ndjson",
                                        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no","X-Session-Mode":"session"})
            else:
                return JSONResponse({"model": body.get("model"),
                                    "message": {"role":"assistant","content": msg},
                                    "done": True},
                                    headers={"X-Session-Mode":"session"})

        # C3) 逐條：抓 SDG（list_sdg + weight_description）
        if st.get("step") == "f_sdg":
            # 1) 保障 plain 來源（若 cms.plain 沒有，就從 parsed.json 摘要）
            plain = (st.get("cms") or {}).get("plain") or ""
            if not plain:
                try:
                    # 統一用模組前綴，避免同名變數陰影
                    sess_dir = os.path.join(sess_base, session_id)
                    plain = parsed_text_mod.extract_plaintext(sess_dir) or ""
                    st.setdefault("cms", {})["plain"] = plain[:20000]
                except Exception:
                    plain = (plain or "")[:20000]

            system, user = prompt_sdg(plain)

            print("Debug: SDG prompt length:", len(user))

            ok, txt = await ask_upstream_json(
                base_url, body.get("model"),
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                timeout_s=settings.upstream_timeout_s,
            )

            print("Debug: Upstream response for SDG:", txt)

            # 2) 鬆綁解析：不管 txt 長怎樣先盡量撈 JSON
            obj = parse_json_loose(txt if ok else "")
            cand_ls = str(obj.get("list_sdg") or "").strip()
            cand_wd = obj.get("weight_description") or {}

            # 3) 規範化 list_sdg：27 位「0/1,」格式
            bits = [b.strip() for b in cand_ls.split(",") if b.strip() != ""]
            valid = (len(bits) == 27 and all(b in ("0","1") for b in bits))
            if not valid:
                bits = ["0"] * 27
            list_sdg = ",".join(bits)

            # 4) 保底：避免全 0 或描述為空（啟發式）
            if all(b == "0" for b in bits) or not isinstance(cand_wd, dict) or not cand_wd:
                fb = fallback_from_plaintext(plain)
                list_sdg = fb.get("list_sdg", list_sdg)
                cand_wd = fb.get("weight_description", cand_wd)


            # 5) 回寫 payload
            st.setdefault("cms", {}).setdefault("pending_payload", {})["list_sdg"] = list_sdg
            st["cms"]["pending_payload"]["weight_description"] = cand_wd

            # 6) 進 aligned、寫狀態
            st["step"] = "aligned"
            write_state(sess_base, session_id, st)

            pretty = json.dumps(st["cms"]["pending_payload"], ensure_ascii=False)
            msg = (
                f"目前草稿（名稱＋理念＋SDG）：\n{pretty}\n\n"
                "如果沒問題，可以回『上傳』；或跟我說要微調哪一欄。"
            )
            append_history(session_id, "assistant", msg, sess_base)
            if want_stream:
                return StreamingResponse(one_shot_ndjson(msg)(),
                                         media_type="application/x-ndjson",
                                         headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no","X-Session-Mode":"session"})
            else:
                return JSONResponse({"model": body.get("model"),
                                     "message": {"role":"assistant","content": msg},
                                     "done": True},
                                    headers={"X-Session-Mode":"session"})


        # D) aligned：等使用者指令「上傳」→ 送出 CMS
        if st.get("step") in ("aligned", "aligned_with_warnings"):
            user_text = _get_last_user_text(messages) or ""
            want_upload = bool(UPLOAD_RE.search(user_text) or YES_RE.search(user_text))  # ← 新增：接受「好」

            if not want_upload:
                # 還沒說要上傳，就提示
                tip = "若看起來沒問題，回覆「上傳」或「好」我就會送到永續系統。"
                append_history(session_id, "assistant", tip, sess_base)
                if want_stream:
                    return StreamingResponse(one_shot_ndjson(tip)(),
                                            media_type="application/x-ndjson",
                                            headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no","X-Session-Mode":"session"})
                else:
                    return JSONResponse({"model": body.get("model"),
                                        "message": {"role":"assistant","content": tip},
                                        "done": True},
                                        headers={"X-Session-Mode":"session"})

            # 真的要上傳
            pending = ((st.get("cms") or {}).get("pending_payload")) or {}
            if not pending:
                msg = "找不到待上傳的參數，請再說「好」讓我重新產生一次。"
                append_history(session_id, "assistant", msg, sess_base)
                if want_stream:
                    return StreamingResponse(one_shot_ndjson(msg)(),
                                            media_type="application/x-ndjson",
                                            headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no","X-Session-Mode":"session"})
                else:
                    return JSONResponse({"model": body.get("model"),
                                        "message": {"role":"assistant","content": msg},
                                        "done": True},
                                        headers={"X-Session-Mode":"session"})

            # 送到 CMS
            pending = validate_and_fix_payload(pending or {})
            status_code, data, raw = await post_cms_upload(pending)

            if 200 <= status_code < 300:
                uuid = data.get("uuid") or data.get("id") or ""
                st["step"] = "uploaded"
                st.setdefault("cms", {})["uuid"] = uuid
                write_state(sess_base, session_id, st)

                url = f"https://nsdgs.4impact.cc/content/{uuid}" if uuid else ""
                msg = (
                    f"✅ 已上傳到永續系統。專案編號：{uuid or '（未回傳編號）'}"
                    + (f"\n連結：{url}" if uuid else "")
                )
                append_history(session_id, "assistant", msg, sess_base)
                if want_stream:
                    return StreamingResponse(one_shot_ndjson(msg)(),
                                            media_type="application/x-ndjson",
                                            headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no","X-Session-Mode":"session"})
                else:
                    return JSONResponse({"model": body.get("model"),
                                        "message": {"role":"assistant","content": msg},
                                        "done": True},
                                        headers={"X-Session-Mode":"session"})
            else:
                # 失敗：把 raw 訊息附上方便除錯
                msg = f"❌ 上傳失敗 (HTTP {status_code})。"
                append_history(session_id, "assistant", msg, sess_base)
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