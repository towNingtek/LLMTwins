# app/routers/chat.py
import requests, random
import json
import aiohttp
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pathlib import Path
from app.session_utils import append_history
from app.services.state_store import read_state, write_state
from app.core.ndjson import ndjson_line, one_shot_ndjson
# from app.core.regexes import YES_RE, UPLOAD_RE
from dotenv import load_dotenv
load_dotenv()

"""
from app.flows.doc_flow import (
    handle_doc_parsed_entry,
    handle_awaiting_confirm,
    prepare_aligning,
    prompt_aligned_tip,
    handle_upload,
)
from app.flows.fields_flow import step_f_name, step_f_philosophy, step_f_sdg
"""
from app.core.streaming import proxy_streaming

router = APIRouter(prefix="/api", tags=["chat"])


def _get_last_user_text(messages):
    for msg in reversed(messages or []):
        if (msg or {}).get("role") == "user":
            return msg.get("content") or ""
    return ""

"""
from fastapi import APIRouter, Request
from starlette.responses import JSONResponse
from pathlib import Path
import requests, random, json

router = APIRouter()
"""

@router.post("/mapping")
async def mapping(request: Request):
    from starlette.responses import StreamingResponse
    print("🚀 /mapping API triggered")

    # 1️⃣ 解析 body
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON body"})

    operator = (body.get("email", "") or "").strip()
    email_list = body.get("email_list", []) or []
    session_id = (body.get("sessionId", "default_session") or "").strip()
    model = body.get("model", "openai/gpt-4o-mini")
    want_stream = bool(body.get("stream", True))

    if not operator or not isinstance(email_list, list):
        return JSONResponse(status_code=400, content={"error": "Missing email or email_list"})

    # 2️⃣ 防呆：email_list 不可包含操作者；去重、過濾空字串
    normalized = []
    seen = set()
    for e in email_list:
        e = (e or "").strip()
        if not e or e == operator or e in seen:
            continue
        seen.add(e)
        normalized.append(e)
    email_list = normalized

    if len(email_list) == 0:
        return JSONResponse(status_code=400, content={"error": "email_list is empty after filtering operator / duplicates"})

    BASE_URL = "https://beta-tplanet-backend.ntsdgs.tw/"

    # 3️⃣ 目錄結構：mapping 下包含操作者與其他帳號
    root_dir = Path("sessions") / session_id / "mapping"
    root_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 Mapping root: {root_dir}")

    all_emails = [operator] + email_list

    # 3-1️⃣ 建立各子資料夾與初始狀態
    for e in all_emails:
        subdir = root_dir / e
        subdir.mkdir(exist_ok=True)
        status_file = subdir / "status.json"
        if not status_file.exists():
            with open(status_file, "w") as f:
                json.dump({"status": "initial"}, f, ensure_ascii=False, indent=2)

    # 4️⃣ 取得各帳號專案
    all_projects = {}
    for e in all_emails:
        try:
            resp = requests.post(f"{BASE_URL}/projects/projects", data={"email": e})
            if resp.status_code == 200:
                all_projects[e] = resp.json().get("projects", [])
            else:
                all_projects[e] = []
        except Exception:
            all_projects[e] = []
        print(f"📦 {e} has {len(all_projects[e])} projects")

    # 5️⃣ 若全員都沒有專案 → 回覆提示
    if all(len(plist) == 0 for plist in all_projects.values()):
        prompt = "目前尚無任何專案可進行媒合，請先在各帳號中建立專案。"
        llm_payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": want_stream,
        }
        response = await proxy_streaming(
            request,
            request.app.state.settings.ollama_base_url,
            json.dumps(llm_payload).encode("utf-8"),
            session_mode=False,
            session_id=None,
            deny_enabled=False,
            deny_guard=None,
            refusal_text="",
            append_history_fn=None,
            sess_base=request.app.state.sess_base,
        )
        return response if want_stream else JSONResponse({"message": prompt})

    # 6️⃣ 準備媒合池（至少一個）
    available = [p for plist in all_projects.values() for p in plist]
    selected = random.sample(available, 2) if len(available) >= 2 else available * 2

    project_infos = []
    for uuid in selected:
        try:
            info_resp = requests.get(f"{BASE_URL}/projects/info/{uuid}")
            if info_resp.status_code == 200:
                project_infos.append(info_resp.json())
        except Exception:
            pass

    # 7️⃣ 更新狀態為 mapping（全員）
    for e in all_emails:
        status_file = (root_dir / e / "status.json")
        with open(status_file, "w") as f:
            json.dump({"status": "mapping"}, f, ensure_ascii=False, indent=2)

    # 8️⃣ 產生媒合草稿 Prompt
    prompt = (
        "請你幫我媒合以下兩個專案，整合成一個 600 字的新專案摘要，"
        "並列出原始的兩個專案名稱。\n" + json.dumps(project_infos, ensure_ascii=False)
    )

    llm_payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": want_stream,
    }

    # 8-1️⃣ 即時建立 project.json 佔位檔
    operator_dir = root_dir / operator
    operator_dir.mkdir(exist_ok=True)
    draft_file = operator_dir / "project.json"
    with open(draft_file, "w") as f:
        json.dump(
            {
                "draft": "(streaming mode: writing in progress)",
                "operator": operator,
                "session_id": session_id,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    # 9️⃣ 呼叫 LLM 串流
    response = await proxy_streaming(
        request,
        request.app.state.settings.ollama_base_url,
        json.dumps(llm_payload).encode("utf-8"),
        session_mode=False,
        session_id=None,
        deny_enabled=False,
        deny_guard=None,
        refusal_text="",
        append_history_fn=None,
        sess_base=request.app.state.sess_base,
    )

    # ⚠️ 若是串流模式，直接回傳（但檔案已存在）
    if want_stream:
        return response

    # 🔟 收集非串流結果 → 寫入真正內容
    content = b""
    async for chunk in response.body_iterator:
        content += chunk

    decoded = content.decode("utf-8", errors="ignore")
    lines = [l.strip() for l in decoded.split("\n") if l.strip()]
    merged = ""
    for line in lines:
        try:
            obj = json.loads(line)
            if obj.get("message", {}).get("content") is not None:
                merged += obj["message"]["content"]
        except Exception:
            continue

    with open(draft_file, "w") as f:
        json.dump(
            {
                "draft": merged,
                "operator": operator,
                "source_projects": selected,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    # 11️⃣ 全員狀態切換為 draft
    for e in all_emails:
        with open(root_dir / e / "status.json", "w") as f:
            json.dump({"status": "draft"}, f, ensure_ascii=False, indent=2)

    return JSONResponse({
        "message": "媒合草稿已生成",
        "draft_file": str(draft_file),
        "status": "draft"
    })

# =========================================================
# 🧩 新增補寫 API：/mapping/update
# =========================================================
@router.post("/mapping/update")
async def mapping_update(request: Request):
    """供前端在串流結束後覆寫 project.json"""
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    session_id = body.get("sessionId", "")
    operator = body.get("email", "")
    content = body.get("draft", "")

    if not session_id or not operator:
        return JSONResponse(status_code=400, content={"error": "Missing sessionId or email"})

    draft_file = Path(f"sessions/{session_id}/mapping/{operator}/project.json")
    draft_file.parent.mkdir(parents=True, exist_ok=True)

    with open(draft_file, "w") as f:
        json.dump(
            {
                "draft": content,
                "operator": operator,
                "session_id": session_id,
                "status": "draft (updated)"
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    return JSONResponse({
        "message": "草稿更新完成",
        "draft_file": str(draft_file)
    })

@router.post("/mapping/revise")
async def mapping_revise(request: Request):
    """stream 模式：保留原內容並追加生成結果"""
    from starlette.responses import StreamingResponse
    import codecs, asyncio

    print("🚀 /mapping/revise (stream append mode)")

    # === 1️⃣ parse request ===
    body = await request.json()
    operator = body.get("email", "").strip()
    session_id = body.get("sessionId", "").strip()
    prompt = body.get("prompt", "").strip()
    model = body.get("model", "openai/gpt-4o-mini")

    if not operator or not session_id or not prompt:
        return JSONResponse(status_code=400, content={"error": "Missing email, sessionId or prompt"})

    # === 2️⃣ load existing project.json ===
    proj_path = Path(f"sessions/{session_id}/mapping/{operator}/project.json")
    proj_path.parent.mkdir(parents=True, exist_ok=True)

    if proj_path.exists():
        with open(proj_path, "r") as f:
            base_data = json.load(f)
    else:
        base_data = {"draft": "", "operator": operator, "session_id": session_id, "status": "revising"}

    # === 3️⃣ prepare full prompt ===
    full_prompt = (
        "你是一位專業政府專案編輯助理。"
        "請根據以下文件內容，按照使用者指示進行補充或修訂。"
        "保持原文風格與格式一致，並直接續寫或修改內容。\n\n"
        f"--- 原始內容 ---\n{base_data.get('draft', '')}\n\n--- 使用者要求 ---\n{prompt}"
    )

    llm_payload = {
        "model": model,
        "messages": [{"role": "user", "content": full_prompt}],
        "stream": True,
    }

    # === 4️⃣ 呼叫 LLM 串流 ===
    response = await proxy_streaming(
        request,
        request.app.state.settings.ollama_base_url,
        json.dumps(llm_payload).encode("utf-8"),
        session_mode=False,
        session_id=None,
        deny_enabled=False,
        deny_guard=None,
        refusal_text="",
        append_history_fn=None,
        sess_base=request.app.state.sess_base,
    )

    decoder = codecs.getincrementaldecoder("utf-8")()
    lock = asyncio.Lock()
    current_draft = base_data.get("draft", "")

    async def stream_and_save():
        nonlocal current_draft
        buffer = ""

        async for chunk in response.body_iterator:
            buffer += decoder.decode(chunk)
            lines = buffer.split("\n")
            buffer = lines[-1]  # keep incomplete

            for line in lines[:-1]:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    delta = obj.get("message", {}).get("content")
                    if delta:
                        current_draft += delta
                        async with lock:
                            with open(proj_path, "w") as f:
                                json.dump(
                                    {
                                        "draft": current_draft,
                                        "operator": operator,
                                        "session_id": session_id,
                                        "status": "revising (streaming)",
                                        "revise_prompt": prompt,
                                    },
                                    f,
                                    ensure_ascii=False,
                                    indent=2,
                                )
                        yield (json.dumps(obj) + "\n").encode("utf-8")
                except Exception:
                    continue

        # ✅ 完成階段
        async with lock:
            with open(proj_path, "w") as f:
                json.dump(
                    {
                        "draft": current_draft,
                        "operator": operator,
                        "session_id": session_id,
                        "status": "revising (done)",
                        "revise_prompt": prompt,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        yield b'{"done": true}\n'

    return StreamingResponse(stream_and_save(), media_type="application/json")

@router.post("/chat")
async def proxy_ollama_chat(request: Request):
    # ---- Settings / Shared ----
    settings = request.app.state.settings
    base_url = settings.ollama_base_url
    sess_base = settings.sess_base
    deny_enabled = settings.deny_enabled
    timeout_s = settings.upstream_timeout_s
    cms_url = settings.cms_upload_url

    # ---- Parse request body ----
    payload_bytes = await request.body()
    try:
        body = json.loads(payload_bytes.decode("utf-8"))
        want_stream = bool(body.get("stream", True))
        messages = body.get("messages") or []
    except Exception:
        body = {}
        want_stream, messages = True, []

    # ---- Guard / session info ----
    deny_guard = getattr(request.app.state, "deny_guard", None)
    refusal_text = (deny_guard.refusal_text if deny_guard else "抱歉，我無法回覆這個問題。")

    session_id = request.query_params.get("session_id")
    session_mode = bool(session_id)

    # ---- Persist user/system messages into history (session mode) ----
    if session_mode:
        for m in messages:
            role = (m or {}).get("role")
            if role in ("user", "system"):
                append_history(session_id, role, (m.get("content") or ""), sess_base)

    # ---- Pre-guard check on last user text ----
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
                    yield ndjson_line({"message": {"role": "assistant", "content": refusal_text}, "done": False})
                    yield ndjson_line({"done": True})

                return StreamingResponse(gen_refuse(), media_type="application/x-ndjson", headers=headers)
            else:
                if session_mode:
                    append_history(session_id, "assistant", refusal_text, sess_base)
                return JSONResponse(
                    {"model": body.get("model"), "message": {"role": "assistant", "content": refusal_text}, "done": True},
                    headers=headers,
                )

    # ===================== Local state-driven flow =====================
    if session_mode:
        try:
            st = read_state(sess_base, session_id)
        except Exception:
            st = {}

    # ===================== Default: forward to upstream =====================
    timeout = aiohttp.ClientTimeout(total=None, connect=10)
    connector = aiohttp.TCPConnector(force_close=False, enable_cleanup_closed=True)
    session = aiohttp.ClientSession(timeout=timeout, connector=connector)

    try:
        # Non-streaming
        if not want_stream:
            resp = await session.post(
                f"{base_url}/api/chat",
                data=payload_bytes,
                headers={"Content-Type": "application/json", "Accept-Encoding": "identity"},
            )
            upstream_txt = await resp.text()
            await resp.release()
            await session.close()

            # 先嘗試把上游當 JSON 直接轉回給前端
            try:
                upstream_json = json.loads(upstream_txt)
            except Exception:
                upstream_json = None

            # session 模式下，把助理回覆寫入歷史
            if session_mode:
                try:
                    if upstream_json and isinstance(upstream_json, dict):
                        content_for_history = ((upstream_json.get("message") or {}).get("content")) \
                                              or upstream_json.get("response") or ""
                    else:
                        content_for_history = upstream_txt
                    if content_for_history:
                        append_history(session_id, "assistant", content_for_history, sess_base)
                except Exception:
                    pass

            if upstream_json:
                # 上游就是合法 JSON → 原封不動回傳
                return JSONResponse(
                    content=upstream_json,
                    headers={"X-Session-Mode": "session" if session_mode else "stateless"},
                )

            # 上游不是合法 JSON → 依 request 的 response_format 合成包裝
            rf = (body.get("response_format") or {}).get("type")
            raw = (upstream_txt or "").strip()

            if rf == "json_object":
                # 盡力從上游純文字中撈出第一段 JSON
                if raw:
                    try:
                        content_obj = json.loads(raw)
                    except Exception:
                        from app.services.json_parse import extract_first_json
                        s = extract_first_json(raw)
                        content_obj = json.loads(s) if s else {}
                else:
                    content_obj = {}
            else:
                # 非 json_object → 當成一般純文字
                content_obj = raw

            envelope = {
                "model": body.get("model"),
                "message": {"role": "assistant", "content": content_obj},
                "done": True,
            }
            return JSONResponse(
                content=envelope,
                headers={"X-Session-Mode": "session" if session_mode else "stateless"},
            )


        # Streaming
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
        # Upstream returned error via proxy_streaming raise
        return JSONResponse(status_code=500, content={"error": str(e)})