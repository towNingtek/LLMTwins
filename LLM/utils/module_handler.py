import os
import ast
import importlib.util

def import_modules_from_directory(directory):
    modules = {}
    for filename in os.listdir(directory):
        if filename.endswith('.py'):
            module_name = os.path.splitext(filename)[0]
            module_path = os.path.join(directory, filename)
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            modules[module_name] = module

    return modules

def get_function_names_from_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        file_content = file.read()

    tree = ast.parse(file_content)
    functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    return functions

def get_functions_from_files(directory):
    all_functions = {}
    for file_name in os.listdir(directory):
        file_path = os.path.join(directory, file_name)
        if os.path.isfile(file_path) and file_path.endswith('.py'):
            functions = get_function_names_from_file(file_path)
            all_functions[file_path] = functions

    return all_functions

def import_function_from_file(file_path, function_name):
    spec = importlib.util.spec_from_file_location("module.name", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, function_name)