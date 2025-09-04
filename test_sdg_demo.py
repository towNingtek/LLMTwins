"""
SDG Demo API 測試腳本
"""

import asyncio
import aiohttp
import json

async def test_sdg_demo():
    """測試 SDG Demo API"""
    
    base_url = "http://localhost:8002"
    
    # 測試案例
    test_cases = [
        {
            "name": "指定 SDG 1,2,3",
            "payload": {
                "sdgs": "1,2,3",
                "model": "llama3.1",
                "stream": False
            }
        },
        {
            "name": "隨機 SDG",
            "payload": {
                "model": "llama3.1",
                "stream": False
            }
        },
        {
            "name": "串流模式測試",
            "payload": {
                "sdgs": "17",
                "stream": True
            }
        }
    ]
    
    async with aiohttp.ClientSession() as session:
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n{'='*50}")
            print(f"測試 {i}: {test_case['name']}")
            print(f"{'='*50}")
            
            try:
                async with session.post(
                    f"{base_url}/api/chat_demo",
                    json=test_case["payload"],
                    headers={"Content-Type": "application/json"}
                ) as resp:
                    
                    if test_case["payload"].get("stream", False):
                        # 處理串流回應
                        print("串流回應:")
                        async for line in resp.content:
                            if line:
                                try:
                                    data = json.loads(line.decode())
                                    if "message" in data:
                                        print(f"內容: {data['message']['content'][:100]}...")
                                    if data.get("done"):
                                        print("串流結束")
                                        break
                                except:
                                    continue
                    else:
                        # 處理一般回應
                        result = await resp.json()
                        print(f"狀態碼: {resp.status}")
                        print(f"分析的 SDG: {result.get('sdgs_analyzed', '未知')}")
                        print(f"載入資料點數: {result.get('data_points_loaded', '未知')}")
                        print(f"回應內容: {result.get('message', {}).get('content', '')[:200]}...")
                        
            except Exception as e:
                print(f"測試失敗: {e}")


def test_csv_loading():
    """測試 CSV 載入功能"""
    import csv
    from pathlib import Path
    
    print("測試 CSV 檔案載入...")
    
    for i in range(1, 18):
        csv_path = Path(f"data/sdgs/{i}.csv")
        if csv_path.exists():
            try:
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    data = list(reader)
                    print(f"SDG {i}: 載入 {len(data)} 筆資料 ✓")
            except Exception as e:
                print(f"SDG {i}: 載入失敗 - {e}")
        else:
            print(f"SDG {i}: 檔案不存在")


if __name__ == "__main__":
    print("開始測試 SDG Demo API")
    
    # 先測試檔案載入
    test_csv_loading()
    
    # 測試 API
    print("\n開始測試 API...")
    asyncio.run(test_sdg_demo())
