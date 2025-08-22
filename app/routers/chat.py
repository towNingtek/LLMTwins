# app/routers/chat.py
import json, asyncio, re, datetime, os
import aiohttp
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse
from app.session_utils import append_history
from app.services.state_utils import read_state, write_state
from app.services.parsed_text import extract_plaintext
from app.services.field_prompts import prompt_name, prompt_philosophy, prompt_sdg
from app.services.demo_mode import in_demo_mode, pick_demo_payload, fake_upload

router = APIRouter(prefix="/api", tags=["chat"])

YES_RE = re.compile(r"(好|好的|是|ok|okay|yes|可以|幫我|開始)", re.I)
NO_RE  = re.compile(r"(先不要|不要|否|no|稍後|等等)", re.I)
UPLOAD_RE = re.compile(r"(上傳|送出|提交|直接上傳|幫我上傳)", re.I)
# ===== 共用：呼叫上游的小工具 =====
DEFAULT_UPSTREAM_TIMEOUT = int(os.getenv("UPSTREAM_TIMEOUT", "180"))

from collections import defaultdict

_SDG_HINTS = {
    "教育": ["4"], "學習": ["4"],
    "能源": ["7"], "再生能源": ["7"], "太陽能": ["7"], "節能": ["7"],
    "就業": ["8"], "經濟": ["8"], "創業": ["8"],
    "產業": ["9"], "創新": ["9"], "基礎設施": ["9"],
    "城市": ["11"], "社區": ["11"], "交通": ["11"], "大眾運輸": ["11"], "無障礙": ["11"],
    "循環": ["12"], "回收": ["12"], "廢棄物": ["12"],
    "氣候": ["13"], "減碳": ["13"], "淨零": ["13"],
    "生態": ["15"], "保育": ["15"], "濕地": ["15"],
    "夥伴": ["17"], "跨域": ["17"], "公私協力": ["17"],
}

def _fallback_from_parsed(plain_text: str):
    bits = ["0"] * 27
    score = defaultdict(int)
    text = (plain_text or "")[:8000]
    for kw, ids in _SDG_HINTS.items():
        if kw in text:
            for sid in ids:
                score[sid] += 1
    top = sorted(score.items(), key=lambda x: (-x[1], int(x[0])))[:4] or [("11", 1)]
    chosen = {sid for sid, _ in top}
    for sid in chosen:
        idx = int(sid) - 1
        if 0 <= idx < 27:
            bits[idx] = "1"
    wd = {k: f"<p>本計畫與 SDG {k} 具關聯，資料有限，將於送審前再精修。</p>" for k in chosen}
    return {"list_sdg": ",".join(bits), "weight_description": wd}


import re, json

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")

def parse_json_loose(txt: str) -> dict:
    """
    盡可能從上游字串撈出『最後一段 JSON 物件』：
    - 支援有 code fence ``` 的情況
    - 支援外層還包一層 {"message":{"content":"{...}"}}
    - 找不到時回 {}
    """
    if not txt:
        return {}
    txt = txt.strip()

    # 情況1：已是物件
    if txt.startswith("{") and txt.endswith("}"):
        try:
            return json.loads(txt)
        except Exception:
            pass

    # 情況2：上游 wrapper：{"message":{"content":"{...}"}}
    try:
        obj = json.loads(txt)
        # 常見包法
        raw = ((obj.get("message") or {}).get("content")) or obj.get("response")
        if isinstance(raw, str):
            return parse_json_loose(raw)
    except Exception:
        pass

    # 情況3：帶 ```json / ``` 包起來
    fence = re.findall(r"```(?:json)?\s*([\s\S]*?)```", txt, flags=re.I)
    if fence:
        for seg in reversed(fence):
            try:
                return json.loads(seg.strip())
            except Exception:
                continue

    # 情況4：從整段撈最後一個 {...}
    blocks = _JSON_BLOCK_RE.findall(txt)
    for seg in reversed(blocks):
        try:
            return json.loads(seg.strip())
        except Exception:
            continue

    return {}

async def _ask_upstream_json(base_url: str, model: str, messages: list, timeout_s: int = DEFAULT_UPSTREAM_TIMEOUT):
    """
    打上游 /api/chat，非串流，回傳 (ok, raw_text)。
    - 逾時 / 連線問題 → (False, "error: ...")
    """
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_s, connect=10)) as s2:
            async with s2.post(f"{base_url}/api/chat",
                               data=json.dumps({"model": model, "stream": False, "messages": messages}, ensure_ascii=False),
                               headers={"Content-Type": "application/json", "Accept-Encoding": "identity"}) as r2:
                txt = await r2.text()
        return True, txt
    except asyncio.TimeoutError:
        return False, "timeout"
    except Exception as e:
        return False, f"error: {e}"

def _normalize_ocr_spaces(text: str) -> str:
    # 把「計 畫 / 國 際 事 務」這類斷字合併
    return re.sub(r"(?<=\S)\s+(?=\S)", "", text)

def _is_all_zero_sdg_str(s: str) -> bool:
    parts = [x.strip() for x in (s or "").split(",") if x.strip() != ""]
    return len(parts) == 27 and all(x == "0" for x in parts)

def _fallback_from_parsed(parsed_clip: str) -> dict:
    """
    從 parsed_clip 粗暴掰一份非空內容：
    - name：從「名 稱 / 計畫名稱 / 計 畫 書」附近抽一句，合併斷字
    - philosophy：從「計畫目的 / 執行內容」抓 2~4 句組一段
    - list_sdg / weight_description：依關鍵字啟發式打 1 並生 <p>…</p>
    """
    text = parsed_clip or ""
    # 1) name
    name = ""
    for m in re.finditer(r"(名\s*稱|計\s*畫\s*名\s*稱|計\s*畫\s*書).{0,30}?\n([^\n]{4,40})", text):
        cand = _normalize_ocr_spaces(m.group(2)).strip("：:|-— \t")
        if 4 <= len(cand) <= 40:
            name = cand
            break

    # 2) philosophy：抽目的/內容段落的前 2~4 句
    ph = ""
    m2 = re.search(r"(計\s*畫\s*目\s*的|問題\s*評\s*析|執\s*行\s*內\s*容|工\s*作\s*項\s*目)[^\n]*\n(.{80,600})", text, re.S)
    if m2:
        blob = _normalize_ocr_spaces(m2.group(2))
        # 句子切分（粗略）
        sents = re.split(r"[。；;]\s*", blob)
        sents = [s.strip() for s in sents if s.strip()]
        ph = "；".join(sents[:4])[:200]

    # 3) SDG 啟發式
    # 先全 0
    bits = ["0"] * 27
    desc = {}

    def set_on(idx: int, ptext: str):
        k = str(idx)
        bits[idx-1] = "1"
        if k not in desc:
            desc[k] = f"<p>{ptext}</p>"

    clean = re.sub(r"\s+", "", text)
    def has(*kw):
        return any((k in text) or (k.replace(" ", "") in clean) for k in kw)

    if has("國 際","國際","兩 岸","兩岸","姐妹市","交流","合作","城市外交","外賓","訪問","互訪"):
        set_on(17, "計畫涉及國際/兩岸合作與城市外交，建立跨域夥伴關係。")
    if has("城 市","城市","觀 光","觀光","旅遊","燈會","友誼燈區","展演","城市韌性"):
        set_on(11, "以觀光與城市展演活動提升城市能見度與社區韌性。")
    if has("產 業","產業","經 濟","經濟","就 業","就業","服務業","觀光產值","招商"):
        set_on(8, "推動觀光及相關服務業帶動就業與經濟成長。")
    if has("農 特 產 品","農特產品","行 銷","行銷","產 業 鏈","在地產業"):
        set_on(21, "連結在地產業與外部市場，推動農特產品行銷。")
    if has("景 點","景點","活動","旅遊","展演","燈會","推廣"):
        set_on(22, "以活動與展演帶動景點能見度與旅遊吸引力。")
    if has("文 化","文化","藝 文","藝文","展 演","在地文化"):
        set_on(19, "透過文化展演與交流，推動在地文化傳播。")
    if has("研 擬","研擬","規 劃","規劃","培 力","培力","知 識","知識","教育","課程","培訓"):
        set_on(24, "涉及規劃與能力培力，強化知識與治理能力。")
    if has("社 群","社群","協 作","協作","公私協力","國際團體","參 與","參與"):
        set_on(26, "跨部門與社群合作，增進集體參與與協作。")
    if has("美 學","美學","城市意象","景觀","裝置","展演美感"):
        set_on(27, "以展演與景觀營造公共美學與城市意象。")

    # 至少保證 4 個為 1（若不足，優先補 17,11,8,22）
    if bits.count("1") < 4:
        for idx in (17,11,8,22):
            set_on(idx, desc.get(str(idx), "與國際交流、觀光與城市活動相關。"))

    result = {
        "name": name or "（待補正式名稱）",
        "philosophy": ph or "本計畫旨在推動國際交流與城市觀光合作，結合展演及在地產業行銷，以提升能見度與經濟效益。",
        "list_sdg": ",".join(bits),
        "weight_description": desc
    }
    # show debug msg
    print("Debug: Fallback upload payload:", json.dumps(result, ensure_ascii=False, indent=2))

    return result

def _is_all_zero_sdg(ls: str) -> bool:
    bits = [b.strip() for b in (ls or "").split(",") if b.strip() != ""]
    # 剛好 27 位，且全部為 0 → 視為無效
    return len(bits) == 27 and all(b == "0" for b in bits)

def _need_repair(p: dict) -> bool:
    """只要有任何一項是『空/無效』，就回 True 代表需要再催一次 LLM。"""

    # Debug show payload
    print("Debug: payload to check:", json.dumps(p, ensure_ascii=False, indent=2))

    if not isinstance(p, dict):
        return True
    name_empty = not str(p.get("name") or "").strip()
    phil_empty = not str(p.get("philosophy") or "").strip()
    ls_invalid = _is_all_zero_sdg(str(p.get("list_sdg") or ""))
    wd = p.get("weight_description")
    wd_empty = (not isinstance(wd, dict)) or (len(wd) == 0)
    return name_empty or phil_empty or ls_invalid or wd_empty

def _extract_first_json(s: str) -> str:
    """從文字中擷取『最大』且括號平衡的 JSON 物件。容錯：移除```json code fence。"""
    if not s:
        return ""
    s = s.strip()
    # 移除 code fence
    if s.startswith("```"):
        s = s.strip("`")
        s = s.replace("json", "", 1) if s.lower().startswith("json") else s
    # 直接是純 JSON
    if s.startswith("{") and s.endswith("}"):
        return s
    # 以堆疊掃描所有 JSON 片段，回最長的一段
    best = ""
    start = -1
    depth = 0
    for i, ch in enumerate(s):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    cand = s[start:i+1]
                    if len(cand) > len(best):
                        best = cand
                    start = -1
    return best

def _validate_and_fix_payload(obj: dict) -> dict:
    """固定 email、不足日期用今年整年、檢查 list_sdg 長度=27、限制 weight_description key 僅為 1 的索引、推 is_budget_revealed。"""
    fixed_email = "forus999@gmail.com"

    # 1) email 固定
    obj["email"] = fixed_email

    # 2) 日期 fallback：抓不到就今年整年
    year = datetime.datetime.now().year
    def _date_or_fallback(k, default):
        v = (obj.get(k) or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            return v
        return default
    start_fb = f"{year}-01-01"
    end_fb   = f"{year}-12-31"
    obj["project_start_date"] = _date_or_fallback("project_start_date", start_fb)
    obj["project_due_date"]   = _date_or_fallback("project_due_date",   end_fb)

    # 3) list_sdg 必須 27 位 0/1
    ls = (obj.get("list_sdg") or "").strip()
    bits = [b.strip() for b in ls.split(",") if b.strip()!=""]
    if len(bits) != 27 or any(b not in ("0","1") for b in bits):
        # 不合法就全部 0（交給下一輪修正也可）
        bits = ["0"] * 27
    obj["list_sdg"] = ",".join(bits)

    # 4) weight_description 只保留 list_sdg=1 的索引鍵
    wd = obj.get("weight_description") or {}
    if not isinstance(wd, dict):
        wd = {}
    ones = {str(i+1) for i,b in enumerate(bits) if b=="1"}
    wd = {k: v for k, v in wd.items() if str(k) in ones}
    obj["weight_description"] = wd

    # 5) budget 與 is_budget_revealed
    try:
        budget = int(obj.get("budget") or 0)
    except Exception:
        budget = 0
    obj["budget"] = budget
    obj["is_budget_revealed"] = bool(budget > 0)

    # 6) org/hoster_email 若不是字串就設為 None
    if obj.get("org") is not None and not isinstance(obj.get("org"), str):
        obj["org"] = None
    if obj.get("hoster_email") is not None and not isinstance(obj.get("hoster_email"), str):
        obj["hoster_email"] = None

    # 7) name/philosophy 至少確保是字串
    obj["name"] = str(obj.get("name") or "").strip()
    obj["philosophy"] = str(obj.get("philosophy") or "").strip()

    return obj

CMS_UPLOAD_URL = "https://beta-tplanet-backend.4impact.cc/projects/upload"

async def _post_cms_upload(payload: dict) -> tuple[int, dict, str]:
    data = {k: (json.dumps(v, ensure_ascii=False) if k=="weight_description" and not isinstance(v, str) else ("" if v is None else str(v)))
            for k, v in payload.items()}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:
        async with s.post(CMS_UPLOAD_URL, data=data) as r:  # 這裡 aiohttp 會自動用 x-www-form-urlencoded
            raw = await r.text()
            try:
                data = json.loads(raw)
            except Exception:
                data = {}
            return r.status, data, raw


def one_shot_ndjson(text: str):
    async def gen():
        yield ndjson_line({"message": {"role": "assistant", "content": text}, "done": False})
        yield ndjson_line({"done": True})
    return gen

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

                    status_code, data, raw = await _post_cms_upload(payload)

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
            ok, txt = await _ask_upstream_json(
                base_url, body.get("model"),
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                timeout_s=DEFAULT_UPSTREAM_TIMEOUT,
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
                ok, txt = await _ask_upstream_json(
                    base_url, body.get("model"),
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    timeout_s=DEFAULT_UPSTREAM_TIMEOUT,
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
            ok, txt = await _ask_upstream_json(base_url, body.get("model"), [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ], timeout_s=DEFAULT_UPSTREAM_TIMEOUT)

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

            ok, txt = await _ask_upstream_json(
                base_url, body.get("model"),
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                timeout_s=DEFAULT_UPSTREAM_TIMEOUT,
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
                fb = _fallback_from_parsed(plain)
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
            pending = _validate_and_fix_payload(pending or {})
            status_code, data, raw = await _post_cms_upload(pending)

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