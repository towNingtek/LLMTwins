def format_html(text):
    # 將文本中的每個換行符 \n 替換成 HTML 的換行標籤 <br>
    html_content = text.replace("\n", "<br>")
    # 包裹在一個 div 標籤中，以便於在 HTML 頁面中正確顯示
    return f"<div>{html_content}</div>"