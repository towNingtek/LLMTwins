# app/routers/chat_demo.py - 完整版
import json
import csv
import random
from pathlib import Path
from typing import List, Dict, Optional
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from app.core.ndjson import ndjson_line, one_shot_ndjson

print("chat_demo.py is being loaded!")

router = APIRouter(prefix="/api", tags=["chat_demo"])

@router.get("/chat_demo/test")
async def test_endpoint():
    """測試端點 - 確認路由是否正確載入"""
    return {"status": "chat_demo router is working!", "message": "路由載入成功"}


class ChatDemoRequest(BaseModel):
    sdgs: Optional[str] = None  # "1,2,3" format
    model: Optional[str] = "llama3.1"
    stream: Optional[bool] = True
    userMessage: Optional[str] = None  # 新增：用戶的聊天內容


def load_sdg_data(sdg_number: int) -> List[Dict]:
    """載入指定 SDG 的 CSV 數據"""
    try:
        csv_path = Path(f"data/sdgs/{sdg_number}.csv")
        
        if not csv_path.exists():
            return []

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            data = list(reader)
            return data
    except Exception as e:
        print(f"Error loading SDG {sdg_number}: {e}")
        return []


def generate_sdg_analysis(sdg_data: Dict[int, List[Dict]], user_message: str = "") -> str:
    """生成 SDG 分析建議 (內建邏輯，不依賴外部 LLM)"""
    if not sdg_data:
        return "沒有找到相關的 SDG 數據。"
    
    # 解析用戶消息中的計劃信息
    plan_name = ""
    user_question = user_message
    
    if "計劃名稱：" in user_message:
        parts = user_message.split("\n")
        for part in parts:
            if part.startswith("計劃名稱："):
                plan_name = part.replace("計劃名稱：", "").strip()
            elif part.startswith("用戶詢問："):
                user_question = part.replace("用戶詢問：", "").strip()
    
    analysis = "🌍 永續發展目標(SDGs)專業分析報告\n\n"
    
    # 如果有計劃名稱，添加計劃相關分析
    if plan_name:
        analysis += f"📋 **分析對象**：{plan_name}\n\n"
    
    if user_question and user_question != user_message:
        analysis += f"❓ **關注焦點**：{user_question}\n\n"
    
    analysis += f"🎯 **涵蓋範圍**：SDG {', '.join(map(str, sorted(sdg_data.keys())))}\n\n"
    
    # 詳細的 SDG 分析
    for sdg_num, data_list in sorted(sdg_data.items()):
        analysis += f"📊 === SDG {sdg_num} 深度分析 ===\n\n"
        
        # 統計面向
        aspects = {}
        for item in data_list:
            aspect = item.get('面向', '未分類')
            aspects[aspect] = aspects.get(aspect, 0) + 1
        
        analysis += f"🔍 **分析維度**：{', '.join(aspects.keys())} (共 {len(data_list)} 項指標)\n\n"
        
        # 重點指標分析
        analysis += "📈 **核心指標與實施路徑**：\n\n"
        for i, item in enumerate(data_list[:3], 1):  # 只顯示前3項
            analysis += f"**{i}. 指標 {item.get('指標編號', 'N/A')}**\n"
            analysis += f"   📄 內容：{item.get('內容', 'N/A')}\n"
            analysis += f"   🏛️ 建議實施單位：{item.get('實施單位建議', 'N/A')}\n"
            
            gov_action = item.get('政府機關可行動作建議', '')
            if gov_action:
                analysis += f"   ⚡ 政府行動方案：{gov_action}\n"
            
            # 如果有用戶問題，提供針對性建議
            if user_question and len(user_question) > 5:
                analysis += f"   💡 針對您的問題「{user_question[:30]}...」的建議：\n"
                analysis += f"      - 此指標可透過{item.get('實施單位建議', '相關部門')}進行推動\n"
                analysis += f"      - 建議優先關注{item.get('面向', '相關面向')}的具體執行\n"
            
            analysis += "\n"
        
        if len(data_list) > 3:
            analysis += f"   📚 *另有 {len(data_list) - 3} 項相關指標可進一步分析*\n\n"
        
        # 地方執行案例
        local_examples = []
        for item in data_list:
            local_content = item.get('南投縣', '')
            if local_content and len(local_content) > 10:
                local_examples.append(local_content[:150] + "...")
                break
        
        if local_examples:
            analysis += f"🏘️ **地方執行案例參考**：\n   {local_examples[0]}\n\n"
        
        analysis += "="*60 + "\n\n"
    
    # 綜合建議部分
    total_indicators = sum(len(data) for data in sdg_data.values())
    sdg_list = sorted(sdg_data.keys())
    
    analysis += "💡 **整合性實施建議**\n\n"
    
    if plan_name:
        analysis += f"針對「**{plan_name}**」專案，結合 SDG {', '.join(map(str, sdg_list))} 的 {total_indicators} 項指標分析：\n\n"
    
    analysis += "**🔄 階段性推動策略**：\n"
    analysis += f"   • **第一階段**（3-6個月）：優先推動可量化且具立即效益的指標\n"
    analysis += f"   • **第二階段**（6-12個月）：建立跨部門協調機制與監測系統\n"
    analysis += f"   • **第三階段**（1-2年）：全面評估成效並調整長期策略\n\n"
    
    analysis += "**🤝 跨目標協同效應**：\n"
    if len(sdg_list) > 1:
        analysis += f"   • SDG {sdg_list[0]} 與 SDG {sdg_list[1]} 具有政策互補性\n"
        analysis += f"   • 可透過整合性政策設計達成多重效益\n"
        analysis += f"   • 建議建立跨部門工作小組統籌執行\n\n"
    
    analysis += "**📊 監測評估框架**：\n"
    analysis += f"   • 建立定期檢討機制（建議每季評估進度）\n"
    analysis += f"   • 設定明確的關鍵績效指標(KPIs)\n"
    analysis += f"   • 透過公民參與提升政策透明度\n\n"
    
    if user_question and len(user_question) > 5:
        analysis += f"**🎯 針對您的具體問題回應**：\n"
        analysis += f"   關於「{user_question}」，基於上述 SDG 分析：\n"
        analysis += f"   • 建議優先關注政策整合性與執行可行性\n"
        analysis += f"   • 可參考地方政府既有執行經驗\n"
        analysis += f"   • 重視利害關係人參與和社會對話\n\n"
    
    analysis += "📈 **預期效益與影響**：\n"
    analysis += f"   • **社會效益**：提升生活品質與社會福祉\n"
    analysis += f"   • **環境效益**：促進永續發展與環境保護\n"
    analysis += f"   • **經濟效益**：創造就業機會與經濟成長\n"
    analysis += f"   • **治理效益**：強化政府效能與公民信任\n\n"
    
    analysis += "---\n\n"
    analysis += f"📋 **報告摘要**：本分析報告涵蓋 {len(sdg_list)} 個 SDG 目標的 {total_indicators} 項具體指標"
    
    if plan_name:
        analysis += f"，針對「{plan_name}」提供專業建議"
    
    analysis += "。建議採取階段性、整合性的推動策略，並建立完善的監測評估機制。"
    
    return analysis


@router.post("/chat_demo")
async def sdg_chat_demo(request: Request):
    """SDG 聊天 Demo API - 增強版支援用戶消息整合"""
    print("chat_demo endpoint called!")
    
    # 解析請求
    try:
        payload_bytes = await request.body()
        body = json.loads(payload_bytes.decode("utf-8"))

        sdgs_param = body.get("sdgs")
        model = body.get("model", "llama3.1")
        want_stream = body.get("stream", True)
        user_message = body.get("userMessage", "")  # 新增：獲取用戶消息

        print(f"Request: sdgs={sdgs_param}, model={model}, stream={want_stream}")
        if user_message:
            print(f"User message: {user_message[:100]}..." if len(user_message) > 100 else f"User message: {user_message}")

    except Exception as e:
        error_msg = f"Invalid request format: {str(e)}"
        print(error_msg)
        raise HTTPException(status_code=400, detail=error_msg)

    # 處理 SDGs 參數
    if sdgs_param:
        try:
            # 解析 "1,2,3" 或 "sdg1,sdg2,sdg3" 格式
            sdg_parts = [x.strip() for x in sdgs_param.split(",")]
            sdg_numbers = []
            
            for part in sdg_parts:
                if part.isdigit():
                    # 純數字格式：'1', '2', '3'
                    sdg_numbers.append(int(part))
                elif part.startswith('sdg') and part[3:].isdigit():
                    # SDG 前綴格式：'sdg1', 'sdg2', 'sdg3'
                    sdg_numbers.append(int(part[3:]))
                else:
                    # 嘗試提取數字
                    import re
                    match = re.search(r'\d+', part)
                    if match:
                        sdg_numbers.append(int(match.group()))
            
            # 只保留有效的 SDG 編號 (1-17)
            sdg_numbers = [x for x in sdg_numbers if 1 <= x <= 17]
            print(f"從參數 '{sdgs_param}' 解析出的 SDG: {sdg_numbers}")
            
        except Exception as e:
            print(f"解析 SDG 參數失敗: {e}")
            sdg_numbers = []
    else:
        sdg_numbers = []
        print("未提供 SDG 參數")

    # 只有在完全沒有有效 SDG 時才隨機選擇
    if not sdg_numbers:
        sdg_numbers = random.sample(range(1, 18), 3)
        print(f"隨機選擇的 SDG: {sdg_numbers}")
    else:
        print(f"使用用戶指定的 SDG: {sdg_numbers}")
    
    print(f"Selected SDG numbers: {sdg_numbers}")

    # 載入 SDG 數據
    sdg_data = {}
    for sdg_num in sdg_numbers:
        data = load_sdg_data(sdg_num)
        if data:
            sdg_data[sdg_num] = data

    print(f"Loaded SDG data for: {list(sdg_data.keys())}")

    if not sdg_data:
        error_msg = "無法載入 SDG 數據，請確認數據檔案是否存在於 data/sdgs/ 目錄。"
        print(error_msg)
        
        if want_stream:
            async def gen_error():
                yield ndjson_line({"message": {"role": "assistant", "content": error_msg}, "done": False})
                yield ndjson_line({"done": True})
            return StreamingResponse(gen_error(), media_type="application/x-ndjson")
        else:
            return JSONResponse({"message": {"role": "assistant", "content": error_msg}, "done": True})

    # 生成分析報告 (使用內建邏輯，整合用戶消息)
    analysis_text = generate_sdg_analysis(sdg_data, user_message)

    # 返回結果
    if want_stream:
        return StreamingResponse(
            one_shot_ndjson(analysis_text)(),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        )
    else:
        return JSONResponse({
            "model": model,
            "message": {"role": "assistant", "content": analysis_text},
            "done": True,
            "sdgs_analyzed": sorted(sdg_numbers),
            "data_points_loaded": sum(len(data) for data in sdg_data.values()),
            "user_context": bool(user_message.strip())
        })

print("chat_demo.py loaded successfully!")