import unicodedata

def preview(text: str, limit: int = 600) -> str:
    """
    安全的文字預覽：全形→半形、限制長度，避免 log 失控。
    """
    if text is None:
        return "<none>"
    if not isinstance(text, str):
        try:
            text = str(text)
        except Exception:
            return "<non-string>"
    s = unicodedata.normalize("NFKC", text)
    return s if len(s) <= limit else f"{s[:limit]} … ({len(s)} chars)"
