# roles/ai_cat/graph.py
from langgraph.graph import StateGraph, END, START 
from typing import Dict, Any

# 導入剛剛修改的 generator node
from roles.ai_cat.nodes.respond_llm import respond_llm_node 

def ai_cat_workflow():
    from roles.ai_cat.state import CatState 
    
    # 關鍵：移除 channels 參數
    graph = StateGraph(CatState) 
    
    # 關鍵：直接註冊 Generator Node
    graph.add_node("respond_llm", respond_llm_node) 

    graph.add_edge(START, "respond_llm")
    graph.add_edge("respond_llm", END)

    return graph.compile()