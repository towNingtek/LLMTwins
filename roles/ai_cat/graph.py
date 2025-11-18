from langgraph.graph import StateGraph
from roles.ai_cat.state import CatState
from roles.ai_cat.nodes.respond import respond_node
from core.role_profiles import load_role_profile


def ai_cat_workflow():
    profile = load_role_profile("ai_cat")

    workflow = StateGraph(CatState)

    async def respond_node_wrapped(state):
        return await respond_node(state, profile)

    workflow.add_node("respond", respond_node_wrapped)

    workflow.set_entry_point("respond")
    workflow.set_finish_point("respond")

    return workflow.compile()