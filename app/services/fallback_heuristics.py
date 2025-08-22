# app/services/fallback_heuristics.py
import re, json
from collections import defaultdict
from typing import Dict, Any

# ---- A) 簡易 SDG 啟發式（從 plain_text 推出 SDG 與描述） ----
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

def fallback_from_plaintext(plain_text: str) -> Dict[str, Any]:
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

# ---- B) 完整欄位啟發式（OCR/段落分析） ----
def _normalize_ocr_spaces(text: str) -> str:
    return re.sub(r"(?<=\S)\s+(?=\S)", "", text)

def fallback_from_parsed_clip(parsed_clip: str) -> Dict[str, Any]:
    """
    產生 name / philosophy / list_sdg / weight_description
    與你原 chat.py 的 _fallback_from_parsed（完整版）邏輯一致。
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
        sents = re.split(r"[。；;]\s*", blob)
        sents = [s.strip() for s in sents if s.strip()]
        ph = "；".join(sents[:4])[:200]

    # 3) SDG 啟發式（同你原版）
    bits = ["0"] * 27
    desc: Dict[str, str] = {}

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

    if bits.count("1") < 4:
        for idx in (17,11,8,22):
            set_on(idx, desc.get(str(idx), "與國際交流、觀光與城市活動相關。"))

    result = {
        "name": name or "（待補正式名稱）",
        "philosophy": ph or "本計畫旨在推動國際交流與城市觀光合作，結合展演及在地產業行銷，以提升能見度與經濟效益。",
        "list_sdg": ",".join(bits),
        "weight_description": desc
    }
    return result

