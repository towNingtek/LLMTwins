# app/routers/chat_demo.py - 升級版：真正的提示工程
import json
import csv
import random
import asyncio
import httpx
from pathlib import Path
from typing import List, Dict, Optional
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from app.core.ndjson import ndjson_line, one_shot_ndjson

router = APIRouter(prefix="/api", tags=["planning"])

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

async def search_project_info(project_name: str) -> Optional[Dict]:
    """呼叫專案搜尋 API"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://beta-tplanet-backend.ntsdgs.tw/projects/search",
                headers={"Content-Type": "application/json"},
                json={"name": project_name},
                timeout=10.0
            )
            
            if response.status_code == 200:
                # 解析回應格式 (True, '{json_data}')
                result = response.text
                if result.startswith("(True, '") and result.endswith("')"):
                    json_str = result[8:-2]  # 移除 (True, ' 和 ')
                    # 處理轉義字符
                    json_str = json_str.replace('\\"', '"').replace('\\r\\n', '\n').replace('\\\\', '\\')
                    project_data = json.loads(json_str)
                    return project_data
                    
        return None
    except Exception as e:
        print(f"Error searching project: {e}")
        return None

def build_enhanced_prompt(project_info: Optional[Dict], sdg_data: Dict[int, List[Dict]], user_question: str, plan_name: str = "") -> str:
    """建構增強版提示工程"""
    
    prompt = """你是南投縣政府的永續發展專業顧問，擁有豐富的政策規劃與 SDG 實施經驗。請基於以下資訊提供專業分析與建議。

## 專案背景資訊"""
    
    if project_info:
        prompt += f"""
**專案名稱：** {project_info.get('name', 'N/A')}
**執行期間：** {project_info.get('period', 'N/A')}
**預算規模：** {project_info.get('budget', 'N/A')} 萬元
**主辦單位：** {project_info.get('hoster', 'N/A')}
**執行範圍：** {project_info.get('location', 'N/A')}

**專案理念：**
{project_info.get('philosophy', 'N/A')}

**重點 SDG 權重：**
{project_info.get('weight_description', 'N/A')}
"""
    elif plan_name:
        prompt += f"""
**計劃名稱：** {plan_name}
"""
    
    prompt += f"""

## 相關 SDG 政策工具與施政案例

針對本次諮詢涉及的 SDG {', '.join(map(str, sorted(sdg_data.keys())))}，南投縣現有政策工具如下：
"""
    
    for sdg_num, data_list in sorted(sdg_data.items()):
        prompt += f"""
### SDG {sdg_num} 政策工具
"""
        for item in data_list:
            prompt += f"""
**指標 {item.get('指標編號', 'N/A')}：** {item.get('內容', 'N/A')}
- 建議實施單位：{item.get('實施單位建議', 'N/A')}
- 政府行動方案：{item.get('政府機關可行動作建議', 'N/A')}
- 南投縣施政案例：{item.get('南投縣施政案例', 'N/A')}
"""
    
    prompt += f"""

## 諮詢問題
{user_question}

## 請提供專業建議
請基於上述專案背景、政策工具與施政案例，針對諮詢問題提供：

1. **問題分析**：深入分析問題的核心與挑戰
2. **政策建議**：結合現有政策工具的具體實施方案
3. **資源整合**：如何善用預算與跨部門協作
4. **執行策略**：階段性推動計畫與關鍵里程碑
5. **風險評估**：可能遭遇的困難與因應措施
6. **成效評估**：量化指標與監測機制建議

請以專業、具體、可操作的方式回應，並充分運用南投縣的在地經驗與資源。
"""
    
    return prompt

async def call_llm_api(prompt: str, model: str, base_url: str, stream_callback=None):
    """呼叫 LLM API - 基於你的 chat.py 架構"""
    import aiohttp
    
    try:
        # 使用 aiohttp（與你的 chat.py 一致）
        timeout = aiohttp.ClientTimeout(total=None, connect=10)
        connector = aiohttp.TCPConnector(force_close=False, enable_cleanup_closed=True)
        
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            # 轉換為 Ollama messages 格式
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "stream": stream_callback is not None
            }
            
            payload_bytes = json.dumps(payload).encode('utf-8')
            
            if stream_callback:
                # 串流模式 - 直接處理並呼叫 callback
                async with session.post(
                    f"{base_url}/api/chat",
                    data=payload_bytes,
                    headers={"Content-Type": "application/json", "Accept-Encoding": "identity"}
                ) as response:
                    async for line in response.content:
                        line_str = line.decode('utf-8').strip()
                        if line_str:
                            try:
                                data = json.loads(line_str)
                                if data.get("message", {}).get("content"):
                                    await stream_callback(data["message"]["content"])
                                if data.get("done", False):
                                    break
                            except json.JSONDecodeError:
                                continue
                # 串流模式不回傳任何值
                return None
            else:
                # 非串流模式
                async with session.post(
                    f"{base_url}/api/chat",
                    data=payload_bytes,
                    headers={"Content-Type": "application/json", "Accept-Encoding": "identity"}
                ) as response:
                    result_text = await response.text()
                    return json.loads(result_text)
                    
    except Exception as e:
        print(f"LLM API error: {e}")
        raise e

@router.post("/planning")
async def planning(request: Request):
    """SDG planning 計劃文案建議- 真正的提示工程版本"""
    
    try:
        settings = request.app.state.settings
        base_url = settings.ollama_base_url
    except Exception as e:
        print(f"Error getting settings: {e}")
        return JSONResponse({"error": f"Settings error: {str(e)}"}, status_code=500)
    
    # 解析請求
    try:
        payload_bytes = await request.body()
        body = json.loads(payload_bytes.decode("utf-8"))

        sdgs_param = body.get("sdgs")
        model = body.get("model", "openai/gpt-4o-mini")
        want_stream = body.get("stream", True)
        user_message = body.get("userMessage", "")
        project_name = body.get("projectName", "")

        print(f"Request: sdgs={sdgs_param}, model={model}, stream={want_stream}, project={project_name}")

    except Exception as e:
        error_msg = f"Invalid request format: {str(e)}"
        print(error_msg)
        raise HTTPException(status_code=400, detail=error_msg)

    # 處理 SDGs 參數
    if sdgs_param:
        try:
            sdg_parts = [x.strip() for x in sdgs_param.split(",")]
            sdg_numbers = []
            
            for part in sdg_parts:
                if part.isdigit():
                    sdg_numbers.append(int(part))
                elif part.startswith('sdg') and part[3:].isdigit():
                    sdg_numbers.append(int(part[3:]))
                else:
                    import re
                    match = re.search(r'\d+', part)
                    if match:
                        sdg_numbers.append(int(match.group()))
            
            sdg_numbers = [x for x in sdg_numbers if 1 <= x <= 17]
            print(f"解析出的 SDG: {sdg_numbers}")
            
        except Exception as e:
            print(f"解析 SDG 參數失敗: {e}")
            sdg_numbers = []
    else:
        sdg_numbers = []

    if not sdg_numbers:
        sdg_numbers = random.sample(range(1, 18), 3)
        print(f"隨機選擇的 SDG: {sdg_numbers}")
    
    # 載入 SDG 數據
    sdg_data = {}
    for sdg_num in sdg_numbers:
        data = load_sdg_data(sdg_num)
        if data:
            sdg_data[sdg_num] = data

    if not sdg_data:
        error_msg = "無法載入 SDG 數據，請確認數據檔案是否存在。"
        if want_stream:
            async def gen_error():
                yield ndjson_line({"message": {"role": "assistant", "content": error_msg}, "done": False})
                yield ndjson_line({"done": True})
            return StreamingResponse(gen_error(), media_type="application/x-ndjson")
        else:
            return JSONResponse({"message": {"role": "assistant", "content": error_msg}, "done": True})

    # 解析用戶訊息
    plan_name = ""
    user_question = user_message
    
    if "計劃名稱：" in user_message:
        parts = user_message.split("\n")
        for part in parts:
            if part.startswith("計劃名稱："):
                plan_name = part.replace("計劃名稱：", "").strip()
            elif part.startswith("用戶詢問："):
                user_question = part.replace("用戶詢問：", "").strip()
    
    # 如果有專案名稱，優先使用專案名稱搜尋
    if project_name:
        plan_name = project_name

    # 搜尋專案資訊
    project_info = None
    if plan_name:
        print(f"搜尋專案資訊: {plan_name}")
        project_info = await search_project_info(plan_name)
        if project_info:
            print(f"找到專案資訊: {project_info.get('name', 'N/A')}")
        else:
            print("未找到專案資訊，使用基本模式")

    # 建構增強版提示工程
    enhanced_prompt = build_enhanced_prompt(project_info, sdg_data, user_question, plan_name)
    print(f"Enhanced prompt length: {len(enhanced_prompt)} characters")

    # 呼叫 LLM API
    if want_stream:
        async def gen_streaming_response():
            """真正的 LLM 串流回應"""
            try:
                # 建立一個 queue 來處理串流數據
                stream_queue = asyncio.Queue()
                llm_finished = False
                
                async def stream_callback(delta):
                    await stream_queue.put(delta)
                
                # 建立 LLM 呼叫任務
                async def llm_task():
                    nonlocal llm_finished
                    try:
                        await call_llm_api(enhanced_prompt, model, base_url, stream_callback)
                    except Exception as e:
                        await stream_queue.put(f"LLM 呼叫失敗：{str(e)}")
                    finally:
                        llm_finished = True
                        await stream_queue.put(None)  # 結束信號
                
                # 啟動 LLM 任務
                llm_task_obj = asyncio.create_task(llm_task())
                
                # 處理串流輸出
                while True:
                    try:
                        # 等待數據或超時
                        delta = await asyncio.wait_for(stream_queue.get(), timeout=1.0)
                        
                        if delta is None:  # 結束信號
                            break
                            
                        # 發送增量內容
                        yield ndjson_line({
                            "message": {
                                "role": "assistant", 
                                "content": delta
                            }, 
                            "done": False
                        })
                        
                    except asyncio.TimeoutError:
                        # 檢查 LLM 任務是否已完成
                        if llm_finished:
                            break
                        continue
                
                # 等待 LLM 任務完成
                await llm_task_obj
                
                # 結束標記
                yield ndjson_line({"done": True})
                
            except Exception as e:
                error_msg = f"串流處理失敗：{str(e)}"
                yield ndjson_line({
                    "message": {"role": "assistant", "content": error_msg}, 
                    "done": False
                })
                yield ndjson_line({"done": True})
        
        return StreamingResponse(
            gen_streaming_response(), 
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no"
            }
        )
    else:
        # 非串流模式
        try:
            result = await call_llm_api(enhanced_prompt, model, base_url)
            content = result.get("response", "無法取得回應")
            
            return JSONResponse({
                "model": model,
                "message": {"role": "assistant", "content": content},
                "done": True,
                "sdgs_analyzed": sorted(sdg_numbers),
                "data_points_loaded": sum(len(data) for data in sdg_data.values()),
                "project_found": project_info is not None,
                "prompt_engineering": True
            })
            
        except Exception as e:
            error_msg = f"LLM 呼叫失敗：{str(e)}"
            return JSONResponse({
                "message": {"role": "assistant", "content": error_msg},
                "done": True,
                "error": True
            }, status_code=500)