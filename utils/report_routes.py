import os
import json
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from jinja2 import Template
from agents.虎科同學.logger_utils import list_vision_logs, load_vision_log

router = APIRouter()

TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <title>🧾 Vision Logs Report</title>
  <style>
    body { font-family: system-ui; margin: 2em; background: #f8f8f8; }
    table { width: 100%; border-collapse: collapse; background: white; }
    th, td { border: 1px solid #ccc; padding: 8px; text-align: left; }
    th { background: #e0e0e0; }
    tr:hover { background: #f0f0f0; }
    a { color: #0078d7; text-decoration: none; }
    a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <h2>📜 Vision Log Reports</h2>
  <table>
    <thead>
      <tr>
        <th>時間</th>
        <th>地點名稱</th>
        <th>分數</th>
        <th>GPT 標籤</th>
      </tr>
    </thead>
    <tbody>
      {% for log in logs %}
      <tr>
        <td>{{ log.timestamp }}</td>
        <td><a href="/report/{{ log.filename }}">{{ log.best_location }}</a></td>
        <td>{{ log.score }}</td>
        <td>{{ log.labels }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</body>
</html>
"""

@router.get("/report", response_class=HTMLResponse)
def list_reports(request: Request):
    files = list_vision_logs()
    logs = []

    for f in files:
        try:
            data = load_vision_log(f)
            logs.append({
                "filename": f,
                "timestamp": data.get("timestamp", ""),
                "best_location": data.get("best_location", {}).get("name", "—"),
                "score": data.get("best_location", {}).get("score", 0),
                "labels": ", ".join(data.get("gpt_labels", [])[:3])
            })
        except Exception as e:
            print(f"⚠️ 無法讀取 {f}: {e}")

    html = Template(TEMPLATE).render(logs=logs)
    return HTMLResponse(content=html)

@router.get("/report/{filename}", response_class=HTMLResponse)
def show_report(filename: str):
    from agents.虎科同學.logger_utils import load_vision_log
    import html

    try:
        data = load_vision_log(filename)
    except Exception as e:
        return HTMLResponse(f"<h3>❌ 無法載入 {filename}</h3><pre>{e}</pre>", status_code=404)

    best = data.get("best_location", {})
    features = data.get("mapped_features", {})
    scores = best.get("scores_detail", [])
    weights = best.get("weights", {})

    html_content = f"""
    <html lang="zh-TW">
    <head>
        <meta charset="utf-8">
        <title>📄 {html.escape(best.get('name', '未知地點'))}</title>
        <style>
            body {{ font-family: system-ui; margin: 2em; background: #fafafa; }}
            h2 {{ margin-bottom: 0.3em; }}
            h3 {{ margin-top: 1.5em; }}
            pre {{ background: #f4f4f4; padding: 1em; border-radius: 8px; }}
            table {{ width: 100%; border-collapse: collapse; background: white; }}
            th, td {{ border: 1px solid #ccc; padding: 6px; text-align: left; }}
            th {{ background: #eaeaea; }}
        </style>
    </head>
    <body>
        <h2>📍 {html.escape(best.get('name', '未知地點'))}</h2>
        <p><b>分數：</b>{best.get('score', 0)}</p>
        <p><b>摘要：</b>{html.escape(best.get('summary', '無摘要'))}</p>

        <h3>🧠 GPT 標籤</h3>
        <pre>{json.dumps(data.get('gpt_labels', []), ensure_ascii=False, indent=2)}</pre>

        <h3>🏗️ 映射後特徵 (BuildingFeatures)</h3>
        <pre>{json.dumps(features, ensure_ascii=False, indent=2)}</pre>

        <h3>📊 各地點得分明細</h3>
        <table>
            <tr><th>地點</th><th>得分</th><th>公式</th></tr>
            {''.join(f"<tr><td>{s['name']}</td><td>{s['score']}</td><td>{s['formula']}</td></tr>" for s in scores)}
        </table>

        <h3>⚖️ 權重設定</h3>
        <pre>{json.dumps(weights, ensure_ascii=False, indent=2)}</pre>

        <p style="margin-top:2em;"><a href="/report">← 返回列表</a></p>
    </body>
    </html>
    """

    return HTMLResponse(html_content)
