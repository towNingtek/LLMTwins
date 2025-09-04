# app/flows/claude_port.py
from __future__ import annotations
import json, re, os, time, logging
from typing import Any, Dict, Tuple, Optional
from datetime import date
import httpx

# 盡量沿用你的 logger，如無則使用標準 logging
try:
    from app.logger import logger  # type: ignore
except Exception:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger("claude_port")

from app.services.json_parse import extract_first_json

# =========================
# util: text helpers
# =========================
def _s(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())

def _head(text: str, n: int) -> str:
    return (text or "")[:n]

def _safe_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        s = extract_first_json(text)
        try:
            return json.loads(s) if s else {}
        except Exception:
            return {}

def _norm_budget_to_int(v: Any) -> int:
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v or "")
    m = re.search(r"([\d,]+)\s*萬", s)
    if m: return int(m.group(1).replace(",", "")) * 10000
    m = re.search(r"([\d,]+)\s*千", s)
    if m: return int(m.group(1).replace(",", "")) * 1000
    m = re.search(r"([\d,]+)", s)
    return int(m.group(1).replace(",", "")) if m else 0

def _norm_date(s: str, fallback: str) -> str:
    s = (s or "").strip().replace("/", "-")
    m = re.match(r"^\d{4}-(0?[1-9]|1[0-2])-(0?[1-9]|[12]\d|3[01])$", s)
    return s if m else fallback

# --- 民國年處理：114年度/114年/民國114年 -> 西元年；年度展開為該年 1/1~12/31 ---
_ROC_YEAR_RE = re.compile(r"(民國)?\s*(\d{2,3})\s*年(?:度)?")
def _roc_to_ad_year(text: str) -> Optional[int]:
    m = _ROC_YEAR_RE.search(text or "")
    if not m:
        return None
    y = int(m.group(2))
    return y + 1911 if y < 1900 else y

def _ensure_list_sdg_27(s: str) -> str:
    """確保 27 維 0/1，不足補 0，多的截斷；位置 18–27 固定為 0（與 shell 規則一致）"""
    try:
        arr = [int(x) for x in str(s).split(",")]
    except Exception:
        arr = []
    arr = (arr + [0]*27)[:27]
    for i in range(17, 27):
        arr[i] = 0
    return ",".join(str(x) for x in arr)

def _default_weight_desc_from_active(active_ids):
    lib = {
        "4":  "透過國際交流促進教育創新與人才培育",
        "8":  "推動產業發展創造經濟機會與就業",
        "11": "建設永續發展的國際友善城市",
        "17": "建立國際夥伴關係促進跨域合作",
    }
    out = {}
    for k in active_ids:
        sk = str(k)
        out[sk] = lib.get(sk, "本項目與該目標具關聯性")
    return out

# =========================
# slice functions（等價 grep/head 行為）
# =========================
def _title_slice(full: str) -> str:
    # shell: grep -o '計.*畫.*\|.*計 畫.*\|.*事 務.*計.*' | head -5 | tr '\n' ' '
    txt = _s(full)
    pats = [r"計.*畫.*", r"計\s+畫.*", r"事\s*務.*計.*"]
    hits = []
    for p in pats:
        for m in re.finditer(p, txt):
            seg = txt[m.start(): m.start()+80]
            hits.append(seg)
            if len(hits) >= 5:
                break
        if len(hits) >= 5:
            break
    return " ".join(hits)

def _budget_slice(full: str) -> str:
    # shell: grep -A 5 -B 5 '經費|預算|千.*元|萬.*元|1,909|1909' | head -c 1000
    txt = _s(full)
    m = re.search(r"(經費|預算|[\d,]+千\s*元|[\d,]+萬\s*元|1,909|1909)", txt)
    if not m:
        return _head(txt, 1000)
    i = m.start()
    lo = max(0, i-500)
    hi = min(len(txt), i+500)
    return txt[lo:hi]

def _date_slice(full: str) -> str:
    # shell: grep -A 3 -B 3 '114.*年|年.*度|期.*間' | head -c 800
    txt = _s(full)
    m = re.search(r"(114.*年|年.*度|期.*間)", txt)
    if not m:
        return _head(txt, 800)
    i = m.start()
    lo = max(0, i-350)
    hi = min(len(txt), i+450)
    return txt[lo:hi][:800]

def _summary_slice(full: str) -> str:
    # shell: grep -A10 -B5 '目的|目標|效益|計 畫.*內|執行.*內容|工作.*項目|國 際.*事 務|兩 岸.*事 務|交 流.*活動' | head -c 1500
    txt = _s(full)
    m = re.search(
        r"(目的|目標|效益|計\s*畫.*內|執行.*內容|工作.*項目|國\s*際.*事\s*務|兩\s*岸.*事\s*務|交\s*流.*活動)",
        txt
    )
    if not m:
        return _head(txt, 1200)
    i = m.start()
    lo = max(0, i-300)
    hi = min(len(txt), i+1200)
    seg = txt[lo:hi][:1500]
    if len(seg) < 200:
        return _head(txt, 1200)
    return seg

def _sdg_slice(full: str) -> str:
    # shell: pages[].text | head -c 2500 | normalize
    return _head(_s(full), 2500)

# =========================
# /api/chat 串流（等價 curl -N）
# =========================
async def _post_chat_stream_content(settings, system_prompt: str, user_prompt: str,
                                    *, temperature: float, max_tokens: int,
                                    top_p: Optional[float]=None,
                                    timeout_s: int = 60) -> str:
    """
    1:1 改寫 shell 的 curl -N：呼叫 SELF_BASE_URL/api/chat（NDJSON/SSE），逐行擷取 message.content。
    如果沒有 SELF_BASE_URL，回落到 Ollama /v1/chat/completions（非串流）。
    """
    model = getattr(settings, "fields_model", "") or os.getenv("FIELDS_MODEL", "qwen2.5:7b-instruct")
    base = getattr(settings, "self_base_url", "") or os.getenv("SELF_BASE_URL", "")

    logger.info("[fields] using model=%s base=%s", model, (getattr(settings, "self_base_url", "") or os.getenv("SELF_BASE_URL", "")) or "(ollama-fallback)")

    if not base:
        # 回落：Ollama OpenAI 相容端點（非 streaming）
        try:
            url = (getattr(settings, "ollama_base_url", "") or os.getenv("OLLAMA_BASE_URL", "")).rstrip("/") + "/v1/chat/completions"
            headers = {"Content-Type": "application/json"}
            auth = getattr(settings, "ollama_auth", None) or os.getenv("OLLAMA_AUTH")
            if auth:
                headers["Authorization"] = f"Bearer {auth}"
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                r = await client.post(url, headers=headers, json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": temperature,
                    "top_p": top_p,
                    "max_tokens": max_tokens,
                    "response_format": {"type": "json_object"},
                })
                r.raise_for_status()
                out = r.json()
                return (out.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
        except Exception:
            return ""

    url = base.rstrip("/") + "/api/chat"
    payload = {
        "model": model,
        "stream": True,
        "options": {"temperature": temperature, "top_p": top_p, "max_tokens": max_tokens},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    buf = []
    headers = {"Content-Type": "application/json", "Accept-Encoding": "identity"}
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            async for raw in resp.aiter_lines():
                if not raw:
                    continue
                line = raw.strip()
                # 容忍 SSE "data: {...}" 前綴
                if line.startswith("data:"):
                    line = line[5:].strip()
                # 等價 shell: 只處理看起來是 JSON 的行
                if not (line.startswith("{") and line.endswith("}")):
                    continue
                try:
                    obj = json.loads(line)
                    msg = (obj.get("message") or {}).get("content") or ""
                    if msg:
                        buf.append(msg)
                except Exception:
                    continue
    return "".join(buf)

# =========================
# 5 段抽取（完全等價 prompts 與流程）
# =========================
async def _extract_name(settings, full: str) -> str:
    SYSTEM_PROMPT = (
        '從公文文件抽取計畫名稱。只輸出 JSON: {"name": "計畫名稱"}\n\n'
        "規則：找出主要計畫名稱，忽略依據文件，移除草案字樣，保持5-50字。"
    )
    USER_PROMPT = f"文件片段：{_title_slice(full)}\n\n請抽取主要計畫名稱（JSON格式）："
    content = await _post_chat_stream_content(settings, SYSTEM_PROMPT, USER_PROMPT, temperature=0.05, max_tokens=100)

    cleaned = content.replace("```json", "").replace("```", "")
    j = _safe_json(cleaned)
    logger.info("[fields][name] raw=%s", j)  # ← 新增：看看模型到底回了什麼

    cleaned = content.replace("```json", "").replace("```", "")
    j = _safe_json(cleaned)
    name = (j.get("name") or "").strip()

    if name:
        return name

    # Fallback：從全文第一行/常見格式猜測
    m = re.search(r"(?:計畫|計劃|專案)\s*名稱[：:]\s*([^\n\r]{4,50})", full)
    if m:
        return m.group(1).strip()
    first_line = (full or "").strip().split()[0] if full else ""
    if 4 <= len(first_line) <= 40:
        return first_line
    return "未知計畫名稱"

async def _extract_budget(settings, full: str) -> int:
    SYSTEM_PROMPT = '從文件抽取總預算金額，轉換為純數字（元）。"1,909 千元" → 1909000。只輸出：{"budget": 數字}'
    USER_PROMPT = f"文本：{_budget_slice(full)}\n\n輸出預算（元）："
    content = await _post_chat_stream_content(settings, SYSTEM_PROMPT, USER_PROMPT, temperature=0.1, max_tokens=80)
    cleaned = content.replace("```json", "").replace("```", "")
    j = _safe_json(cleaned)
    val = _norm_budget_to_int(j.get("budget"))
    if val > 0:
        return val

    # --- Fallback：從切片 & 全文用正則補抓 ---
    slice_txt = _budget_slice(full)
    m = re.search(r"([\d,]+)\s*萬\s*元", slice_txt)
    if m:
        try:
            return int(m.group(1).replace(",", "")) * 10000
        except Exception:
            pass
    m = re.search(r"([\d,]+)\s*千\s*元", slice_txt)
    if m:
        try:
            return int(m.group(1).replace(",", "")) * 1000
        except Exception:
            pass
    m = re.search(r"([\d,]+)\s*元", slice_txt)
    if m:
        try:
            return int(m.group(1).replace(",", ""))
        except Exception:
            pass

    # 再掃一遍全文
    m = re.search(r"([\d,]+)\s*(萬|千)?\s*元", full)
    if m:
        raw = int(m.group(1).replace(",", ""))
        unit = m.group(2) or ""
        if unit == "萬": return raw * 10000
        if unit == "千": return raw * 1000
        return raw

    return 0


async def _extract_dates(settings, full: str) -> Tuple[str, str]:
    SYSTEM_PROMPT = '抽取計畫執行期間，處理民國年轉換。"114年度" → start: 2025-01-01, end: 2025-12-31。只輸出：{"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}'
    USER_PROMPT = f"文本：{_date_slice(full)}\n\n輸出執行期間："
    content = await _post_chat_stream_content(settings, SYSTEM_PROMPT, USER_PROMPT, temperature=0.05, max_tokens=100)
    cleaned = content.replace("```json", "").replace("```", "")
    j = _safe_json(cleaned)

    # 先吃模型輸出
    y = date.today().year
    start = _norm_date(j.get("start_date"), f"{y}-01-01")
    end   = _norm_date(j.get("end_date"),   f"{y}-12-31")

    # 再做民國年容錯（如果模型給的是「114年度」等）
    if not (j.get("start_date") and "-" in str(j.get("start_date"))):
        ad = _roc_to_ad_year(_date_slice(full))
        if ad:
            start = f"{ad}-01-01"
    if not (j.get("end_date") and "-" in str(j.get("end_date"))):
        ad = _roc_to_ad_year(_date_slice(full))
        if ad:
            end = f"{ad}-12-31"

    return start, end

async def _generate_philosophy(settings, full: str, name: str) -> str:
    SYSTEM_PROMPT = (
        "從政府計畫文件生成計畫理念摘要。\n\n"
        "任務：\n"
        "1. 仔細閱讀提供的計畫文件內容\n"
        "2. 基於實際文件內容生成 120-180 字的計畫理念\n"
        "3. 必須包含：計畫目標、執行方法、受益對象、預期效益\n"
        "4. 使用正式但易懂的政府文件語調\n\n"
        "重要要求：\n"
        "- 必須基於提供的文件內容，不得編造內容\n"
        "- 準確反映計畫的實際目標與方法\n"
        "- 保持與原文件的一致性\n"
        "- 字數控制在 120-180 字\n"
        "- 分成 3-4 句完整表達\n\n"
        "重要：只輸出純 JSON，不要解釋，不要用 markdown。\n"
        '格式：{"philosophy": "計畫理念內容"}'
    )
    USER_PROMPT = (
        "請基於以下計畫文件，生成120-180字的計畫理念摘要：\n\n"
        f"計畫名稱：{name}\n"
        f"計畫內容：{_summary_slice(full)}\n\n"
        "要求：\n"
        "1. 字數必須達到120-180字\n"
        "2. 適當擴充執行方法與預期效益的描述\n"
        "3. 可包含更多具體執行內容細節\n"
        "4. 嚴格基於上述文件內容，不得編造無關內容\n\n"
        "請生成詳細的計畫理念："
    )
    content = await _post_chat_stream_content(settings, SYSTEM_PROMPT, USER_PROMPT, temperature=0.2, top_p=0.8, max_tokens=400, timeout_s=60)
    cleaned = content.replace("```json", "").replace("```", "")
    j = _safe_json(cleaned)
    out = (j.get("philosophy") or "").strip()
    if not out:
        out = "本計畫旨在推動國際交流與合作，提升地方競爭力。"
    # 與 shell 體驗一致：>180 截斷；<120 僅告警，不強補
    if len(out) > 180:
        out = out[:180]
    return out

async def _classify_sdgs(settings, full: str) -> Tuple[str, Dict[str, str]]:
    SYSTEM_PROMPT = (
        "你是 SDGs 分類專家，需要分析政府計畫並判斷其對應的永續發展目標。\n\n"
        "SDGs 對應表（只需要前17個）：\n位置 1-17: SDG1-SDG17 (聯合國永續發展目標)\n位置 18-27: 設為 0 (不使用)\n\n"
        "SDGs 對應說明：\n"
        "- SDG4 (教育): 教育創新、數位素養、人才培育、國際交流學習\n"
        "- SDG8 (就業): 經濟成長、就業機會、產業發展、國際商務\n"
        "- SDG11 (城市): 永續城市、社區發展、國際友善城市、基礎設施\n"
        "- SDG17 (夥伴): 國際合作、跨域合作、夥伴關係、兩岸事務\n\n"
        "本土指標說明：\n- 位置 18-27: 全部設為 0 (此系統不使用)\n\n"
        "任務：\n1. 仔細分析計畫內容\n2. 判斷哪些 SDGs 高度相關 (設為1)\n3. 為相關的 SDGs 寫 30-50 字的權重描述\n\n"
        "輸出格式（必須包含完整27個位置）：\n"
        '{\n  "list_sdg": "0,0,0,1,0,0,0,1,0,0,1,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0",\n'
        '  "weight_description": {\n'
        '    "4": "透過國際交流促進教育創新與人才培育",\n'
        '    "8": "推動產業發展創造經濟機會與就業",\n'
        '    "11": "建設永續發展的國際友善城市",\n'
        '    "17": "建立國際夥伴關係促進跨域合作"\n'
        "  }\n}\n\n"
        "重要：\n1. list_sdg 必須包含完整27個數字（用逗號分隔）\n"
        "2. 位置1-17：選擇相關的SDGs設為1\n3. 位置18-27：必須全部設為0\n"
        "4. 這個計畫應該對應：SDG4(教育), SDG8(經濟), SDG11(城市), SDG17(夥伴)\n\n"
        "重要：只輸出純 JSON，不要解釋。"
    )
    USER_PROMPT = (
        "請分析以下計畫內容，判斷對應的 SDGs 和本土指標：\n\n"
        "計畫名稱：國際事務推動運用計畫\n"
        f"計畫內容：{_sdg_slice(full)}\n\n"
        "請提供 27 維度的分類結果和權重描述："
    )
    content = await _post_chat_stream_content(settings, SYSTEM_PROMPT, USER_PROMPT, temperature=0.2, top_p=0.9, max_tokens=800, timeout_s=90)
    cleaned = content.replace("```json", "").replace("```", "")
    j = _safe_json(cleaned)
    list_sdg = _ensure_list_sdg_27(j.get("list_sdg") or "")
    wdesc = j.get("weight_description")
    if not isinstance(wdesc, dict) or not wdesc:
        arr = [int(x) for x in list_sdg.split(",")]
        active = [i+1 for i, v in enumerate(arr) if v == 1]
        wdesc = _default_weight_desc_from_active([str(a) for a in active])
    else:
        wdesc = {str(k): str(v) for k, v in wdesc.items() if str(k).strip().isdigit()}
    return list_sdg, wdesc

# =========================
# 對外：整合 payload（1:1 呈現 shell 的 UI 與流程）
# =========================
async def build_integrated_fields(*, settings, full_text: str) -> Dict[str, Any]:
    """
    golden sample 等價版：將 scripts/rag/claude/test_integrated_fields.sh 逐段改寫成 Python。
    - 2,500 字上限、同切片與 prompts
    - /api/chat 串流 NDJSON/SSE 擷取 message.content
    - 同 fallback 規則
    - 會把 payload 存到 scripts/rag/claude/integrated_test_result.json
    - 補齊 log 使輸出接近 shell 畫面
    """
    total_start = time.time()

    # 頁首橫幅（貼近 shell）
    logger.info("==================================================")
    logger.info("🚀 LLMTwins 整合欄位抽取測試")
    logger.info("==================================================")
    logger.info("目標：生成完整的 CMS 上傳 payload")
    logger.info("測試檔案：parsed.json")

    # 與 shell 一致：先把全文壓到 2,500 字並正規化空白
    full = _head(_s(full_text or ""), 2500)
    logger.info("")
    logger.info("📄 文件內容長度: %d 字元", len(full_text or ""))

    # 1) 標題
    logger.info("")
    logger.info("🔍 [1/5] 正在抽取計畫名稱...")
    name = await _extract_name(settings, full)
    logger.info("   ✅ 計畫名稱: %s", name or "（空）")

    # 2) 預算
    logger.info("")
    logger.info("💰 [2/5] 正在抽取預算金額...")
    budget = await _extract_budget(settings, full)
    if not isinstance(budget, int):
        budget = 0
    logger.info("   ✅ 預算金額: %s 元", f"{budget:,}")

    # 3) 期間（含民國年處理）
    logger.info("")
    logger.info("📅 [3/5] 正在抽取執行期間...")
    y = date.today().year
    start, end = await _extract_dates(settings, full)
    if not start: start = f"{y}-01-01"
    if not end:   end   = f"{y}-12-31"
    logger.info("   ✅ 執行期間: %s ~ %s", start, end)

    # 4) 計畫理念（120–180 字；<120 僅警告，>180 截斷）
    logger.info("")
    logger.info("📝 [4/5] 正在生成計畫理念...")
    philosophy = await _generate_philosophy(settings, full, name)
    plen = len(philosophy or "")
    logger.info("   ✅ 計畫理念: %d 字", plen)
    if plen < 120:
        logger.info("   ⚠️ 字數不足（%d字），建議提高模型輸出或補充一兩句。", plen)
    elif plen < 130:
        logger.info("   ⚠️ 字數接近要求 (%d字)", plen)

    # 5) SDGs（確保 27 維，18–27 固定 0）
    logger.info("")
    logger.info("🎯 [5/5] 正在進行 SDGs 分類...")
    list_sdg, weight_description = await _classify_sdgs(settings, full)
    if not list_sdg:
        list_sdg = "0,0,0,1,0,0,0,1,0,0,1,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0"
    if not isinstance(weight_description, dict) or not weight_description:
        weight_description = {}

    try:
        sdg_arr = [int(x) for x in list_sdg.split(",")]
        active_cnt = sum(1 for v in sdg_arr if v == 1)
        len_ok = (len(sdg_arr) == 27)
    except Exception:
        sdg_arr, active_cnt, len_ok = [], 0, False
    logger.info("   ✅ SDGs 分類: 啟用 %d 個目標", active_cnt)
    logger.info("   ✅ 陣列長度%s (27個元素)", "正確" if len_ok else "錯誤")

    # 橫幅+耗時
    elapsed = int(time.time() - total_start)
    logger.info("")
    logger.info("==================================================")
    logger.info("🎉 整合測試完成！總耗時: %s 秒", elapsed)
    logger.info("==================================================")
    logger.info("📋 正在構建 CMS Payload...")
    logger.info("")

    # === 構建 payload（與 shell 完全一致） ===
    payload = {
        "email": "minamj@nantou.gov.tw",
        "name": name,
        "project_start_date": start,
        "project_due_date": end,
        "philosophy": philosophy,
        "budget": int(budget or 0),
        "org": "南投縣政府",
        "hoster_email": "contact@county.gov.tw",
        "list_sdg": list_sdg,
        "weight_description": weight_description or {},
        "is_budget_revealed": True,
        "project_type": "0"
    }

    # 顯示生成的 Payload（與 shell 類似）
    logger.info("📋 生成的 CMS Payload:")
    logger.info(json.dumps(payload, ensure_ascii=False, indent=2))
    logger.info("")

    # 成功率統計（列與 shell 對齊）
    logger.info("==================================================")
    logger.info("✅ 成功率統計")
    logger.info("==================================================")
    logger.info("標題抽取: %s", "✅ 成功" if (name and name != "") else "❌ 失敗")
    logger.info("預算抽取: %s", "✅ 成功" if (isinstance(budget, int) and budget != 0) else "❌ 失敗")
    logger.info("日期抽取: %s", "✅ 成功" if (start and end) else "❌ 失敗")
    logger.info("摘要生成: %s", "✅ 成功" if (len(philosophy or "") > 50) else "❌ 失敗")
    logger.info("SDGs分類: %s", "✅ 成功" if (active_cnt > 2 and len_ok) else "❌ 失敗")
    logger.info("")
    logger.info("🚀 下一步：")
    logger.info("1. 將此 payload 送至 CMS API 測試")
    logger.info("2. 整合至 LLMTwins 的 prompt_* 函數")
    logger.info("3. 建立信心分數評估機制")

    # === 存檔（等價 shell 的 integrated_test_result.json） ===
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))  # -> repo 根目錄
        out_path = os.path.join(base_dir, "scripts", "rag", "claude", "integrated_test_result.json")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.info("")
        logger.info("📁 結果已儲存至: %s", out_path)
    except Exception as e:
        logger.info("無法儲存 integrated_test_result.json: %s", e)

    return payload