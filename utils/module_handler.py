import os
import importlib.util
from typing import List, Callable
from phi.agent import Agent

def load_module(file_path: str, module_name: str):
    """動態載入一個 Python 模組"""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def load_agents_from_directory(directory: str) -> Agent:
    """
    從指定目錄載入 agent 設定和所有工具函數
    
    Args:
        directory (str): agents 所在的目錄路徑
        
    Returns:
        Agent: 創建好的 agent 實例
    """
    agent_creator = None
    
    # 首先找到並載入 agent.py
    agent_path = os.path.join(directory, 'agent.py')
    if os.path.exists(agent_path):
        try:
            agent_module = load_module(agent_path, 'agent')
            agent_creator = getattr(agent_module, 'create_agent', None)
        except Exception as e:
            print(f"載入 agent.py 時發生錯誤: {str(e)}")
            raise
    
    if not agent_creator:
        raise ValueError(f"在 {directory} 中找不到 agent.py 或 create_agent 函數")
        
    # 創建 agent
    try:
        agent = agent_creator()
        return agent
    except Exception as e:
        print(f"創建 agent 時發生錯誤: {str(e)}")
        raise