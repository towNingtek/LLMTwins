# roles/ai_cat/graph.py
from pydantic import BaseModel
from langgraph.graph import StateGraph, END
from roles.ai_cat.nodes.respond_llm import respond_llm_node

class State(BaseModel):
    messages: list = []

def ai_cat_workflow():
    graph = StateGraph(State)

    # Node
    graph.add_node("respond_llm", respond_llm_node)

    # Required entry
    graph.add_edge("__start__", "respond_llm")

    # Finish
    graph.add_edge("respond_llm", END)

    return graph.compile()