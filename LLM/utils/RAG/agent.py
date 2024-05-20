import os
import json
from langchain_core.tools import Tool
from langchain.agents import load_tools
from langchain.agents import initialize_agent
from langchain.agents import AgentType
from LLM.utils.module_handler import import_function_from_file, get_functions_from_files

class Agent():
    def __init__(self, llm):
        self.llm = llm

    def serpapi(self, message):
        tools = load_tools(["serpapi"], llm=self.llm)
        agent = initialize_agent(tools, self.llm, agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION, verbose=False)
        return agent.invoke(message)
    
    def load_rag_tools(self, prompt):
        obj_params = prompt.json()

        list_arg_tools = []
        directory = os.getenv("PATH_RAG_TOOLS")
        functions_dict = get_functions_from_files(directory)

        for file_path, functions in functions_dict.items():
            for function_name in functions:
                function = import_function_from_file(file_path, function_name)
                wrapped_function = lambda input_data, func=function, params=json.dumps(obj_params, ensure_ascii=False): func(params)

                tool = Tool(
                    name = function_name,
                    func = wrapped_function,
                    description = f"Wrapped function {function_name} with custom message"
                )
                list_arg_tools.append(tool)

        return list_arg_tools

    def custom(self, profile, prompt):
        list_rag_tools = self.load_rag_tools(prompt)
        tools = load_tools([], llm=self.llm)

        agent = initialize_agent(
            tools + list_rag_tools,
            self.llm,
            agent = AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            handle_parsing_errors = True,
            max_execution_time = 30,
            verbose = False
        )

        try:
            result = agent.invoke({"input": prompt.message + "請用正體中文 (zh-TW) 回答。"})
            return result["output"]
        except Exception as e:
            print("Error:", str(e))
            return str(e)