import os
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