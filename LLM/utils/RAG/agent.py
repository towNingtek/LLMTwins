import re
import os
import json
from langchain_core.tools import Tool
from langchain.agents import load_tools
from langchain.agents import initialize_agent
from langchain.agents import AgentType
from LLM.utils.module_handler import import_function_from_file, get_functions_from_files
from LLM.utils.format import format_html

def debug_print(prefix, value):
    """
    打印調試信息
    """
    print(f"\n=== {prefix} ===")
    print(f"Type: {type(value)}")
    print(f"Value: {value}")
    if isinstance(value, dict):
        print("Dict content:")
        for k, v in value.items():
            print(f"  {k}: ({type(v)}) {v}")
    print("=" * (len(prefix) + 8))

def is_valid_response(response):
    """
    檢查回應是否為有效的字串型態
    """
    # debug_print("Validating Response", response)

    # 檢查是否為None
    if response is None:
        print("Response is None")
        return False

    # 檢查是否為字串類型
    if not isinstance(response, str):
        print(f"Response is not string, but {type(response)}")
        try:
            if isinstance(response, (dict, list)):
                response = json.dumps(response, ensure_ascii=False)
                # debug_print("Converted to JSON string", response)
                return True
        except Exception as e:
            print(f"JSON conversion failed: {str(e)}")
            return False
        return False

    # 檢查是否為空字串或只包含空白
    if len(str(response).strip()) == 0:
        print("Response is empty or whitespace")
        return False

    # 檢查是否為無效的物件表示
    invalid_responses = [
        "[object Object]",
        "undefined",
        "null",
        "NaN",
        "{}"
    ]

    if str(response).strip() in invalid_responses:
        print(f"Response is invalid: {response}")
        return False

    print("Response is valid")
    return True

def wrap_tool_response(func):
    """
    裝飾器: 包裝 tool 函數的回傳值
    """
    def wrapper(*args, **kwargs):
        try:
            print(f"\n=== Executing tool: {func.__name__} ===")
            result = func(*args, **kwargs)
            # debug_print(f"Tool {func.__name__} raw result", result)

            # 如果結果是字典或列表，轉換為JSON字串
            if isinstance(result, (dict, list)):
                json_result = json.dumps(result, ensure_ascii=False)
                # debug_print(f"Tool {func.__name__} converted result", json_result)
                return json_result

            # 如果結果是字串，直接返回
            if isinstance(result, str):
                return result

            # 其他類型，轉換為字串
            str_result = str(result)
            # debug_print(f"Tool {func.__name__} stringified result", str_result)
            return str_result
        except Exception as e:
            print(f"Tool execution error in {func.__name__}: {str(e)}")
            return str(e)
    return wrapper

class Agent():
    def __init__(self, llm):
        self.llm = llm

    def _handle_invalid_response(self, prompt, postfix_prompt=""):
        """處理無效回應的通用方法"""
        print("\n=== Handling invalid response ===")
        response = self.llm.invoke(prompt.message + postfix_prompt + "請用正體中文 (zh-TW) 回答。")

        # 處理 AIMessage 物件
        if hasattr(response, 'content'):
            response = response.content

        # debug_print("LLM fallback response", response)
        return response

    def load_rag_tools(self, prompt):
        print("\n=== Loading RAG tools ===")
        obj_params = prompt.json()
        # debug_print("RAG parameters", obj_params)

        functions_dict = {}
        list_arg_tools = []
        directory = os.getenv("PATH_RAG_TOOLS")

        try:
            functions_dict = get_functions_from_files(directory + prompt.role + "/")
        except Exception as e:
            print(f"Error loading role-specific tools: {str(e)}")
            functions_dict = get_functions_from_files(directory + "/")

        for file_path, functions in functions_dict.items():
            print(f"\nLoading tools from: {file_path}")
            for function_name in functions:
                print(f"Loading function: {function_name}")
                function = import_function_from_file(file_path, function_name)

                @wrap_tool_response
                def wrapped_function(input_data, func=function, params=obj_params):  # 直接傳入 obj_params 而不是轉換為字串
                    try:
                        result = func(params)
                        if result is None:
                            return "無相關資料"
                        return result
                    except Exception as e:
                        print(f"Error in {function_name}: {str(e)}")
                        return f"執行 {function_name} 時發生錯誤：{str(e)}"

                tool = Tool(
                    name=function_name,
                    func=wrapped_function,
                    description=f"Wrapped function {function_name} with custom message"
                )
                list_arg_tools.append(tool)

        print(f"Loaded {len(list_arg_tools)} tools")
        return list_arg_tools

    def custom(self, profile, prompt):
        print("\n=== Starting custom agent execution ===")
        list_rag_tools = self.load_rag_tools(prompt)
        tools = load_tools([], llm=self.llm)
        agent = initialize_agent(
            tools + list_rag_tools,
            self.llm,
            agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            handle_parsing_errors=True,
            max_execution_time=90,
            verbose=True  # 開啟 verbose 以查看 agent 執行過程
        )

        try:
            postifx_prompt = ""
            if prompt.format and prompt.format == "html":
                postifx_prompt = "請使用 HTML 格式，並將回答包含在一個<div>標籤中。"

            input_message = {"input": prompt.message + postifx_prompt + "請用正體中文 (zh-TW) 回答。"}
            # debug_print("Agent input", input_message)

            result = agent.invoke(input_message)
            # debug_print("Agent raw result", result)

            # 確保 result 是字典且含有 output
            if not isinstance(result, dict) or "output" not in result:
                print("Invalid result format")
                return self._handle_invalid_response(prompt, postifx_prompt)

            response = result["output"]
            # debug_print("Extracted response", response)

            if "Agent stopped due to iteration limit or time limit" in response:
                print("Agent stopped due to limits")
                return self._handle_invalid_response(prompt, postifx_prompt)

            if prompt.format and prompt.format == "html":
                html_content = re.search(r"```html(.*?)```", response, re.DOTALL)
                if html_content:
                    response = format_html(html_content.group(1).strip())
                else:
                    response = format_html(response.strip())
                # debug_print("HTML formatted response", response)

            if not is_valid_response(response):
                print("Response validation failed")
                return self._handle_invalid_response(prompt, postifx_prompt)

            # debug_print("Final response", response)
            return response

        except Exception as e:
            print(f"\n=== Error in custom agent ===\nError type: {type(e)}\nError message: {str(e)}")
            return self._handle_invalid_response(prompt, postifx_prompt)