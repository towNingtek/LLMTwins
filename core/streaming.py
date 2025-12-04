# core/streaming.py
"""Streaming utilities for LangGraph workflows."""

import json
from typing import Any, AsyncGenerator

async def stream_langgraph_workflow(
    workflow,
    initial_state: Any,
) -> AsyncGenerator[str, None]:
    """
    A dedicated stream processor for LangGraph workflows, supporting token-by-token streaming
    """

    # Initial
    inputs = initial_state

    # Increase recursion limits for debugging
    config = {"recursion_limit": 50}

    # Use astream_events to capture custom events (token-by-token streaming)
    async for event in workflow.astream_events(inputs, config=config, version="v2"):
        event_type = event.get("event")

        # Listen for custom events: store_token
        if event_type == "on_custom_event":
            event_name = event.get("name")

            if event_name == "store_token":
                # Extract token chunk
                data = event.get("data", {})
                chunk = data.get("chunk", "")
                stage = data.get("stage", "")

                if chunk:
                    # Send token to the front end in real time
                    token_data = {
                        "type": "token",
                        "content": chunk,
                    }

                    # If there is a stage marker, add it to the output
                    if stage:
                        token_data["stage"] = stage

                    yield json.dumps(token_data, ensure_ascii=False) + "\n"

        # Listen for Node end events (optional, for debugging)
        elif event_type == "on_chain_end":
            pass

    # Process ended
    yield json.dumps({"type": "done"}) + "\n"
