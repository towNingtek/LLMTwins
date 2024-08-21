import re
import os
import json
from langchain_core.tools import Tool
from langchain_community.agent_toolkits.load_tools import load_tools
from langchain.agents import AgentExecutor, create_react_agent
from LLM.utils.module_handler import import_function_from_file, get_functions_from_files
from LLM.utils.format import format_html
from langchain import hub

class Agent():
    def __init__(self, llm):
        self.llm = llm
    
    def load_rag_tools(self, prompt):
        obj_params = prompt.json()
        functions_dict = {}

        list_arg_tools = []
        directory = os.getenv("PATH_RAG_TOOLS")

        functions_dict = get_functions_from_files(directory + "/")

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
        agent = None
        prompt_ = hub.pull("hwchase17/react")

        try:
            agent = create_react_agent(
                self.llm,
                tools + list_rag_tools,
                prompt=prompt_,
            )
            # Execute your prompt or other logic here
        except Exception as e:
            # Handle the error accordingly
            print(f"An error occurred: {e}")

        agent_executor = AgentExecutor(agent=agent, tools=tools + list_rag_tools)

        try:
            postifx_prompt = ""
            if prompt.format and prompt.format == "html":
                postifx_prompt = "請使用 HTML 格式，並將回答包含在一個 <div>標籤中。"

            result = agent_executor.invoke({"input": prompt.message + postifx_prompt + "請用正體中文 (zh-TW) 回答。"})
            if "Agent stopped due to iteration limit or time limit" in result["output"]:
                response = self.llm.invoke(prompt.message + postifx_prompt + "請用正體中文 (zh-TW) 回答。")
                return response
            
            if prompt.format and prompt.format == "html":
                html_content = re.search(r"```html(.*?)```", result["output"], re.DOTALL)
                if html_content:
                    response = format_html(html_content.group(1).strip())
                else:
                    response = format_html(result["output"].strip())
                return response
            else:
                return result["output"]
        except Exception as e:
            print("Error:", str(e))
            return str(e)
