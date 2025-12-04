# roles/ai_cat/graph.py
from langgraph.graph import StateGraph, START, END
from roles.ai_cat.tools import tool_executor_node
from roles.ai_cat.nodes.respond_llm import respond_llm_node
from roles.ai_cat.nodes.analyze import analyze_node

# Routing function: Determines the next Node based on the 'next' key in the state
def router(state):
    """The name of the next Node is determined by the value of the 'next' attribute in the status"""
    return state.next

def ai_cat_workflow():
    from roles.ai_cat.state import CatState

    graph = StateGraph(CatState)

    graph.add_node("analyze", analyze_node)
    graph.add_node("respond_llm", respond_llm_node)
    graph.add_node("call_tool", tool_executor_node)

    # Edges definition
    graph.add_edge(START, "analyze")

    # LLM thinking
    graph.add_edge("analyze", "respond_llm")

    # The router's output ('call_tool' or 'end') determines the next path
    graph.add_conditional_edges(
        "respond_llm",
        router,
        {
            "call_tool": "call_tool",
            "end": END
        }
    )

    # Feedback Edge: After the tool finishes execution, the results are sent back to LLM for further processing
    graph.add_edge("call_tool", "respond_llm")

    # Graph compile
    return graph.compile(debug=True)