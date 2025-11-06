curl -X POST 'https://tplanet-backend-nantou-gov.ntsdgs.tw/projects/upload' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'email=minamj@nantou.gov.tw' \
  --data-urlencode 'name=南投縣數位通服務整備計畫' \
  --data-urlencode 'project_start_date=2025-01-01' \
  --data-urlencode 'project_due_date=2025-12-31' \
  --data-urlencode 'philosophy=本計畫旨在提升數位通服務，強化在地數位協作能力。' \
  --data-urlencode 'budget=12000000' \
  --data-urlencode 'org=數位處' \
  --data-urlencode 'hoster_email=contact@county.gov.tw' \
  # --data-urlencode 'relate_people=10' \
  --data-urlencode 'list_sdg=0,0,0,1,0,0,0,1,1,0,1,1,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0' \
  --data-urlencode 'weight_description={"3":"<p>透過教育創新，提升數位素養和技能，促進終身學習。</p>","7":"<p>推動地方組織和企業的數位轉型，創造就業機會和經濟增長。</p>","8":"<p>利用生成式 AI 技術，促進產業創新和基礎設施發展。</p>","10":"<p>支持地方創生，提升城鄉社區的可持續性和韌性。</p>","11":"<p>確保生成式 AI 的應用符合可持續消費和生產模式。</p>","16":"<p>3</p>"}'
  --data-urlencode 'is_budget_revealed=true'
