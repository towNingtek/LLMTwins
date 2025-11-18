import importlib

def load_workflow(role: str):
    module_path = f"roles.{role}.graph"
    module = importlib.import_module(module_path)
    return module.workflow
