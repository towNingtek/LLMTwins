from langchain.agents import tool

@tool
def basic(str_obj: str) -> str:
    """Basic Tool."""

    return ("我是大語言模型建構而成的數位孿生。")
