# app/services/demo_mode.py
import os, uuid, random, copy, json
from datetime import datetime, timedelta

DEMO_MODE = True
CMS_DEMO_BASE = "https://beta-tplanet-backend.4impact.cc/projects/upload"

# 完整的 demo 資料，包含所有必要欄位
_DEMO_CANDIDATES = [
    {
        "email": "forus999@gmail.com",
        "name": "國際事務推動運用計畫",
        "project_start_date": "2025-01-01",
        "project_due_date": "2025-12-31",
        "philosophy": "依據南投縣政府國際及兩岸事務推動委員會設置要點暨投資區邀請計畫，辦理南投縣政府國際及兩岸事務推動委員會議及邀請區邀請等事宜。",
        "budget": "1909000",
        "org": "計劃處",
        "hoster_email": "contact@county.gov.tw",
        "list_sdg": "0,0,1,0,0,0,0,1,1,0,1,0,1,0,0,0,1,0,0,0,0,0,0,0,0,0,0",
        "weight_description": {
            "2": "<p>促進國際友好交流與文化活動，提升市民健康福祉。</p>",
            "7": "<p>透過國際合作與招商引資，創造就業機會與經濟成長。</p>",
            "8": "<p>建設國際交流基礎設施，促進產業創新發展。</p>",
            "10": "<p>強化城市外交與國際連結，提升城鄉韌性與魅力。</p>",
            "12": "<p>推動永續國際合作模式，促進負責任的發展。</p>",
            "16": "<p>建立跨域國際夥伴關係，擴大合作網絡。</p>"
        },
        "is_budget_revealed": "true"
    },
    {
        "email": "forus999@gmail.com",
        "name": "兩岸事務推動與交流計畫",
        "project_start_date": "2025-01-01",
        "project_due_date": "2025-12-31",
        "philosophy": "協助規劃本縣與姐妹市及其他重要城市間有關文化、觀光、產業等各項交流活動，促進兩岸和平發展與區域合作。",
        "budget": "1909000",
        "org": "計劃處",
        "hoster_email": "contact@county.gov.tw",
        "list_sdg": "0,0,0,1,0,0,0,1,0,0,1,0,0,0,0,1,1,0,0,0,0,0,0,0,0,0,0",
        "weight_description": {
            "3": "<p>透過兩岸教育交流，提升人才培育與終身學習。</p>",
            "7": "<p>推動兩岸經貿合作，創造就業與經濟發展機會。</p>",
            "10": "<p>建立兩岸友好城市關係，促進區域永續發展。</p>",
            "15": "<p>促進兩岸和平對話，建立互信合作機制。</p>",
            "16": "<p>強化兩岸夥伴關係，推動區域整合發展。</p>"
        },
        "is_budget_revealed": "true"
    },
    {
        "email": "forus999@gmail.com",
        "name": "國際招商引資推動計畫",
        "project_start_date": "2025-01-01",
        "project_due_date": "2025-12-31",
        "philosophy": "有關國際及兩岸事務政策研擬事宜，協助規劃招商引資活動，有關本縣與國際間各項交流合作事宜。",
        "budget": "1909000",
        "org": "計劃處",
        "hoster_email": "contact@county.gov.tw",
        "list_sdg": "0,0,0,0,0,0,0,1,1,1,1,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0",
        "weight_description": {
            "7": "<p>透過國際招商引資，創造在地就業機會與經濟成長。</p>",
            "8": "<p>吸引國際投資，促進產業創新與基礎設施發展。</p>",
            "9": "<p>縮短城鄉發展差距，促進包容性經濟成長。</p>",
            "10": "<p>建立國際投資合作機制，提升區域競爭力。</p>",
            "16": "<p>建立國際投資夥伴關係，擴大合作網絡。</p>"
        },
        "is_budget_revealed": "true"
    },
    {
        "email": "forus999@gmail.com",
        "name": "國際文化觀光推廣計畫",
        "project_start_date": "2025-01-01",
        "project_due_date": "2025-12-31",
        "philosophy": "協助規劃本縣與姐妹市及其他重要城市間有關文化、觀光等各項交流活動，提升南投縣國際能見度與觀光競爭力。",
        "budget": "1909000",
        "org": "計劃處",
        "hoster_email": "contact@county.gov.tw",
        "list_sdg": "0,0,1,1,0,0,0,1,1,0,1,1,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0",
        "weight_description": {
            "2": "<p>推廣文化觀光活動，促進民眾身心健康與福祉。</p>",
            "3": "<p>透過文化交流教育，傳承在地文化與終身學習。</p>",
            "7": "<p>發展文化觀光產業，創造就業機會與經濟效益。</p>",
            "8": "<p>建設文化觀光基礎設施，促進產業創新。</p>",
            "10": "<p>打造文化觀光品牌，提升城市永續發展。</p>",
            "11": "<p>推動文化觀光永續發展模式。</p>",
            "16": "<p>建立國際文化觀光合作夥伴關係。</p>"
        },
        "is_budget_revealed": "true"
    },
    {
        "email": "forus999@gmail.com",
        "name": "國際農特產品行銷計畫",
        "project_start_date": "2025-01-01",
        "project_due_date": "2025-12-31",
        "philosophy": "有關本縣農特產品行銷國際之協調聯繫事宜，透過國際交流活動推廣南投優質農特產品，拓展國際市場。",
        "budget": "1909000",
        "org": "計劃處",
        "hoster_email": "contact@county.gov.tw",
        "list_sdg": "0,1,0,0,0,0,0,1,1,0,0,1,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0",
        "weight_description": {
            "1": "<p>改善農民收入，消除農村貧困問題。</p>",
            "7": "<p>拓展農特產品國際市場，創造就業與經濟成長。</p>",
            "8": "<p>建立農特產品國際行銷通路與創新模式。</p>",
            "11": "<p>推動農特產品永續生產與消費模式。</p>",
            "16": "<p>建立農特產品國際行銷夥伴關係。</p>"
        },
        "is_budget_revealed": "true"
    },
    {
        "email": "forus999@gmail.com",
        "name": "國際外賓接待服務計畫",
        "project_start_date": "2025-01-01",
        "project_due_date": "2025-12-31",
        "philosophy": "辦理國際及兩岸外賓接待及出國參訪事宜，提升南投縣政府國際形象與外交能力，深化國際友好關係。",
        "budget": "1909000",
        "org": "計劃處",
        "hoster_email": "contact@county.gov.tw",
        "list_sdg": "0,0,1,1,0,0,0,0,0,0,1,0,0,0,0,1,1,0,0,0,0,0,0,0,0,0,0",
        "weight_description": {
            "2": "<p>提供優質接待服務，促進國際友好關係。</p>",
            "3": "<p>透過國際交流學習，提升政府治理能力。</p>",
            "10": "<p>建立友好城市關係，促進永續發展合作。</p>",
            "15": "<p>推動和平外交，建立互信合作機制。</p>",
            "16": "<p>強化國際夥伴關係，促進多邊合作。</p>"
        },
        "is_budget_revealed": "true"
    },
    {
        "email": "forus999@gmail.com",
        "name": "姐妹市交流深化計畫",
        "project_start_date": "2025-01-01",
        "project_due_date": "2025-12-31",
        "philosophy": "協助規劃本縣與姐妹市間各項實質交流合作，深化友好關係，推動文化、教育、經貿等多元合作發展。",
        "budget": "1909000",
        "org": "計劃處",
        "hoster_email": "contact@county.gov.tw",
        "list_sdg": "0,0,0,1,1,0,0,1,0,0,1,0,0,0,0,1,1,0,0,0,0,0,0,0,0,0,0",
        "weight_description": {
            "3": "<p>推動姐妹市教育交流，促進人才培育發展。</p>",
            "4": "<p>促進姐妹市性別平等交流與合作。</p>",
            "7": "<p>深化姐妹市經貿合作，創造互利共贏。</p>",
            "10": "<p>建立姐妹市永續發展合作機制。</p>",
            "15": "<p>推動姐妹市和平交流，促進友好關係。</p>",
            "16": "<p>強化姐妹市夥伴關係，擴大合作領域。</p>"
        },
        "is_budget_revealed": "true"
    },
    {
        "email": "forus999@gmail.com",
        "name": "國際參訪學習計畫",
        "project_start_date": "2025-01-01",
        "project_due_date": "2025-12-31",
        "philosophy": "依當來交流參訪行程等各項交流活動，學習國際先進經驗，提升本縣治理能力與國際競爭力。",
        "budget": "1909000",
        "org": "計劃處",
        "hoster_email": "contact@county.gov.tw",
        "list_sdg": "0,0,0,1,0,0,0,0,1,0,1,0,0,0,0,1,1,0,0,0,0,0,0,0,0,0,0",
        "weight_description": {
            "3": "<p>透過國際參訪學習，提升公務人員專業能力。</p>",
            "8": "<p>學習國際創新做法，促進產業發展升級。</p>",
            "10": "<p>借鑑國際城市經驗，提升永續發展能力。</p>",
            "15": "<p>學習國際治理經驗，提升政府效能。</p>",
            "16": "<p>建立國際學習夥伴關係，促進知識交流。</p>"
        },
        "is_budget_revealed": "true"
    },
    {
        "email": "forus999@gmail.com",
        "name": "中國大陸地區交流計畫",
        "project_start_date": "2025-01-01",
        "project_due_date": "2025-12-31",
        "philosophy": "依當來交流參訪行程中國大陸參訪行程，推動兩岸和平交流，促進經貿文化合作發展。",
        "budget": "1909000",
        "org": "計劃處",
        "hoster_email": "contact@county.gov.tw",
        "list_sdg": "0,0,0,0,0,0,0,1,0,0,1,0,0,0,0,1,1,0,0,0,0,0,0,0,0,0,0",
        "weight_description": {
            "7": "<p>推動兩岸經貿交流，創造就業與經濟機會。</p>",
            "10": "<p>促進兩岸城市交流，建立友好合作關係。</p>",
            "15": "<p>推動兩岸和平發展，維護區域穩定。</p>",
            "16": "<p>建立兩岸合作夥伴關係，促進共同發展。</p>"
        },
        "is_budget_revealed": "true"
    },
    {
        "email": "forus999@gmail.com",
        "name": "國際事務委員會運作計畫",
        "project_start_date": "2025-01-01",
        "project_due_date": "2025-12-31",
        "philosophy": "召開國際及兩岸事務推動委員會，統籌規劃國際事務政策，建立跨局處協調合作機制，提升國際事務推動效能。",
        "budget": "1909000",
        "org": "計劃處",
        "hoster_email": "contact@county.gov.tw",
        "list_sdg": "0,0,0,0,0,0,0,0,1,0,1,0,0,0,0,1,1,0,0,0,0,0,0,0,0,0,0",
        "weight_description": {
            "8": "<p>建立國際事務推動基礎機制，促進創新發展。</p>",
            "10": "<p>統籌國際事務政策，提升城市永續發展能力。</p>",
            "15": "<p>建立透明治理機制，提升政府效能。</p>",
            "16": "<p>建立跨局處合作夥伴關係，促進政策統合。</p>"
        },
        "is_budget_revealed": "true"
    }
]

def in_demo_mode() -> bool:
    return DEMO_MODE

def pick_demo_payload() -> dict:
    """回傳一份 pending_payload（扁平 dict），供 aligned/上傳直接使用。"""
    if not _DEMO_CANDIDATES:
        # 如果沒有候選資料，回傳最基本的預設值
        return {
            "email": "demo@example.com",
            "name": "測試專案",
            "project_start_date": "2025-01-01",
            "project_due_date": "2025-12-31", 
            "philosophy": "這是一個測試專案。",
            "budget": "1000000",
            "org": "測試單位",
            "hoster_email": "test@example.com",
            "list_sdg": "0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0",
            "weight_description": {},
            "is_budget_revealed": "true"
        }
    
    cand = random.choice(_DEMO_CANDIDATES)
    result = copy.deepcopy(cand)
    
    # 確保 weight_description 是字串格式（因為 _post_cms_upload 會處理 JSON 轉換）
    if isinstance(result.get("weight_description"), dict):
        # 保持為 dict，讓 _post_cms_upload 處理轉換
        pass
    
    return result

def fake_upload(pending: dict) -> dict:
    """模擬上傳，產生 UUID 與可點連結。"""
    rid = str(uuid.uuid4())
    url = f"{CMS_DEMO_BASE}/preview/{rid}"
    return {"uuid": rid, "url": url, "status": "ok", "payload": pending}