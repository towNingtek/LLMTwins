import re

def format_html(text):
    """
    格式化文本為乾淨的 HTML 格式，並添加樣式控制字體大小

    Args:
        text: 原始文本

    Returns:
        str: 格式化後的 HTML 文本
    """
    # 先嘗試提取 HTML 代碼塊
    html_block_match = re.search(r'```html\s*(.*?)\s*```', text, re.DOTALL)
    
    # 添加樣式控制，讓藍色文字變小
    css_style = """
    <style>
        /* 控制所有帶有藍色的文字元素 */
        .blue-text, p, li {
            font-size: 14px !important; /* 設定較小的字體大小 */
        }
        /* 如果藍色文字是特定的標題 */
        h1, h2, h3, h4, h5, h6 {
            font-size: 16px !important;
        }
    </style>
    """

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

        # 組合完整內容，添加 CSS 樣式
        final_content = [css_style]
        if before_block:
            final_content.append(before_block)
        final_content.append(html_content)
        if after_block:
            final_content.append(after_block)

        return "<div>" + "<br>".join(final_content) + "</div>"

    # 如果沒有 HTML 代碼塊，移除可能存在的標記
    cleaned_text = re.sub(r'```html|```|\"html', '', text)

    # 確保內容被 div 包裹，並添加 CSS 樣式
    if not re.search(r'<div.*?>.*?</div>', cleaned_text, re.DOTALL):
        cleaned_text = f"{css_style}<div>{cleaned_text}</div>"
    else:
        # 在第一個 div 標籤前添加 CSS 樣式
        cleaned_text = re.sub(r'(<div.*?>)', f'{css_style}\\1', cleaned_text, 1)

    return cleaned_text