"""Role loader for dynamically loading workflows, tools, and executors."""

import importlib
import pkgutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple


def load_all_roles(
    roles_path: Path,
) -> Tuple[Dict[str, Callable], Dict[str, Callable], Dict[str, List]]:
    """
    Load all roles from the specified directory.

    Returns:
        Tuple of (WORKFLOWS, ROLE_TOOL_EXECUTORS, ROLE_TOOLS)
    """
    workflows: Dict[str, Any] = {}
    role_tool_executors: Dict[str, Any] = {}
    role_tools: Dict[str, list] = {}

    for module in pkgutil.iter_modules([str(roles_path)]):
        role_name = module.name
        try:
            # -----------------------------
            # Load workflow: roles/{role}/graph.py
            # -----------------------------
            graph_module = importlib.import_module(f"roles.{role_name}.graph")
            fn_name = f"{role_name}_workflow"
            workflow_fn = getattr(graph_module, fn_name, None)

            if workflow_fn:
                workflows[role_name] = workflow_fn
                print(f"[LLMTwins] Loaded workflow for: {role_name}")
            else:
                print(f"[LLMTwins] No workflow for: {role_name}")

            # -----------------------------
            # Load tools: roles/{role}/tools.py
            # -----------------------------
            tools_schema = []
            executor_fn = None

            try:
                tool_module = importlib.import_module(f"roles.{role_name}.tools")

                # Load schema
                tools_schema = getattr(tool_module, "TOOLS", [])

                # Executor
                executor_fn = getattr(tool_module, "tool_executor", None)

            except Exception as e:
                print(f"[LLMTwins] Tools load error for {role_name}: {e}")

            # Record tool schema (even empty list)
            role_tools[role_name] = tools_schema
            print(f"[LLMTwins] Loaded tools ({len(tools_schema)}) for: {role_name}")

            # Record executor
            if executor_fn:
                role_tool_executors[role_name] = executor_fn
                print(f"[LLMTwins] Loaded executor for: {role_name}")
            else:
                print(f"[LLMTwins] No executor for: {role_name}")

        except Exception as e:
            print(f"[LLMTwins] Failed to load role {role_name}: {e}")

    return workflows, role_tool_executors, role_tools
