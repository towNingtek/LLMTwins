import re

def format_html(text):
    """
    格式化文本為乾淨的 HTML 格式

    Args:
        text: 原始文本

    Returns:
        str: 格式化後的 HTML 文本
    """
    # 先嘗試提取 HTML 代碼塊
    html_block_match = re.search(r'```html\s*(.*?)\s*```', text, re.DOTALL)

    if html_block_match:
        # 取得代碼塊內的 HTML 內容
        html_content = html_block_match.group(1).strip()

        # 提取代碼塊之前和之後的文字
        before_block = text[:html_block_match.start()].strip()
        after_block = text[html_block_match.end():].strip()

        # 如果 HTML 內容已經包含 div 標籤，直接使用
        if re.search(r'<div.*?>.*?</div>', html_content, re.DOTALL):
            html_content = html_content
        else:
            html_content = f"<div>{html_content}</div>"

        # 組合完整內容
        final_content = []
        if before_block:
            final_content.append(before_block)
        final_content.append(html_content)
        if after_block:
            final_content.append(after_block)

        return "<div>" + "<br>".join(final_content) + "</div>"

    # 如果沒有 HTML 代碼塊，移除可能存在的標記
    cleaned_text = re.sub(r'```html|```|\"html', '', text)

    # 確保內容被 div 包裹
    if not re.search(r'<div.*?>.*?</div>', cleaned_text, re.DOTALL):
        cleaned_text = f"<div>{cleaned_text}</div>"

    return cleaned_text
