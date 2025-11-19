# roles/ai_cat/graph.py
from langgraph.graph import StateGraph, START, END

def ai_cat_workflow():
    from roles.ai_cat.state import CatState
    from roles.ai_cat.nodes.respond_llm import respond_llm_node

    graph = StateGraph(CatState)

    graph.add_node("respond_llm", respond_llm_node)
    graph.add_edge(START, "respond_llm")
    graph.add_edge("respond_llm", END)

    return graph.compile()