import os
import ast
import pygsheets
from langchain_openai import ChatOpenAI
from langchain.llms import HuggingFaceEndpoint
from LLM.utils.gdrive import initialize_drive_service, list_files_in_drive_folder
from LLM.utils.gsheet import write_to_cell
from LLM.langchain.chains import create_sequential_chain
from langchain.callbacks.base import BaseCallbackHandler
from LLM.utils.format import format_html
from LLM.utils.module_handler import import_modules_from_directory
from LLM.utils.RAG.document_loader import DocumentLoader
from LLM.utils.RAG.agent import Agent
from callbacks import *

class CallbackHandler(BaseCallbackHandler):
    def __init__(self, api_table) -> None:
        super().__init__()
        self.api_table = api_table

    def process_data(self, input_data, i):
        # Get if input_data in api_table and get the api name
        api_name = None
        if input_data["value"] in self.api_table:
            api_name = self.api_table[input_data["value"]]
        else:
            return input_data["value"]

        # Execute the api callback function
        callbacks = import_modules_from_directory('callbacks')
        functions = {}
        for module_name, module in callbacks.items():
            functions.update({name: getattr(module, name) for name in dir(module) if callable(getattr(module, name))})

        # Use the extracted function name to retrieve and execute the function from the functions dictionary
        if api_name in functions:
            result = functions[api_name](input_data, i)
            return result
        else:
            return input_data

class DigitalTwins:
    def __init__(self):
        self.llm = None
        self.templates_profile = """你是{name}，{description}。"""
        self.api_intent = None
        self.api_table = None
        self.templates_intent = """請根據用戶的訊息，回傳一個 API 意圖。注意:
        1. 你只能回答在 {api_intent} 中的選項。
        2. 如果你不知道答案，請回答"無法識別"。
        問題：
        """

        self.service = initialize_drive_service(os.getenv("CREDENTIALS_FILE"))
        self.api_table = {}

    def set_model(self, model = None):
        if (model == None):
            self.llm = ChatOpenAI(model = "gpt-4o", temperature = 0)
        else:
            print(f"Model is set to {model}.")
            self.llm = HuggingFaceEndpoint(repo_id = model, huggingfacehub_api_token = os.getenv("HUGGINGFACEHUB_API_TOKEN"))

    # Update_llm_twins function
    def register_llm_twins(self, name, description):
        list_llm_name = list_files_in_drive_folder(self.service, os.getenv("GDRIVE_LLM_ROOT_PATH"))
        file_id = None
        # 在 list_llm_name 中尋找匹配的文件名
        matched_file = next((item for item in list_llm_name if item['name'] == name), None)
        if not matched_file:
            file_id = os.getenv("GSHEET_FOR_TEMPLATE_OF_LLM_PROFILE")
            new_file_name = name
            file_metadata = {
                "name": new_file_name
            }
            response = self.service.files().copy(fileId=file_id, body=file_metadata).execute()
            file_id = response.get('id')
        else:
            file_id = matched_file["file_id"]

        # 使用 pygsheets 打開匹配的文件
        gc = pygsheets.authorize(service_file = os.getenv("CREDENTIALS_FILE"))
        sh = gc.open_by_url("https://docs.google.com/spreadsheets/d/" + file_id + "/edit?usp=sharing")
        worksheet = sh.worksheet_by_title("Profile")

        # 寫入資料
        worksheet = sh.worksheet_by_title("Profile")
        write_to_cell(worksheet, "B1", name)
        write_to_cell(worksheet, "B2", description)

        # 讀取 APIs 表
        worksheet = sh.worksheet_by_title("APIs")
        data = worksheet.get_all_values(include_tailing_empty_rows=False)
        for index, row in enumerate(data):
            if index != 0:  # 跳過第一行
                if len(row) >= 2 and row[0] and row[1]:
                    self.api_table[row[0]] = row[1]

        return True, {"職稱":name, "描述": description}, self.api_table

    def prompt(self, profile, prompt):
        result = True
        response = None

        if (prompt.type == "llm"):
            self.templates_profile = self.templates_profile.format(name = profile[0], description = profile[1])
            result, response = self.invoke(self.llm, self.templates_profile + prompt.message, prompt.format)
        elif (prompt.type == "intent_recognition"):
            result, response = self.intent_recognition(profile, prompt.message)
        elif (prompt.type == "chains"):
            result, response = self.chains(profile, prompt.injection, prompt.message, prompt.format)
        elif (prompt.type == "RAG"):
            result, response = self.rag(self.llm, profile, prompt)

        return result, response

    def load_API_table(self, name):
        list_llm_name = list_files_in_drive_folder(self.service, os.getenv("GDRIVE_LLM_ROOT_PATH"))
        file_id = None
        # 在 list_llm_name 中尋找匹配的文件名
        matched_file = next((item for item in list_llm_name if item['name'] == name), None)
        if not matched_file:
            file_id = os.getenv("GSHEET_FOR_TEMPLATE_OF_LLM_PROFILE")
            new_file_name = name
            file_metadata = {
                "name": new_file_name
            }
            response = self.service.files().copy(fileId=file_id, body=file_metadata).execute()
            file_id = response.get('id')
        else:
            file_id = matched_file["file_id"]

        # 使用 pygsheets 打開匹配的文件
        gc = pygsheets.authorize(service_file = os.getenv("CREDENTIALS_FILE"))
        sh = gc.open_by_url("https://docs.google.com/spreadsheets/d/" + file_id + "/edit?usp=sharing")
        worksheet = sh.worksheet_by_title("APIs")

        data = worksheet.get_all_values(include_tailing_empty_rows=False)
        for index, row in enumerate(data):
            if index != 0:  # 跳過第一行
                if len(row) >= 2 and row[0] and row[1]:
                    self.api_table[row[0]] = row[1]
                else:
                    return None

        return self.api_table

    def intent_recognition(self, profile, user_input):
        result = True
        response = None

        # Get API table
        api_table = self.load_API_table(profile[0])

        response = None
        self.templates_intent = self.templates_intent.format(api_intent = api_table)
        result, response = self.invoke(self.llm, self.templates_intent + user_input)

        return result, response

    def chains(self, profile, injection, user_input, format):
        result = True
        response = None

        # Get API table
        api_table = self.load_API_table(profile[0])

        # Create a template for the API intent
        self.templates_intent = self.templates_intent.format(api_intent = api_table)

        # Return 403 if not injection
        if not injection:
            return False, "Injection is required."

        # Create a profile template
        self.templates_profile = self.templates_profile.format(name = profile[0], description = profile[1])

        # Create a callback handler
        callback_handler = CallbackHandler(api_table)
        response_chain = create_sequential_chain(self.llm, self.templates_profile, callback_handler, injection)

        # Invoke the chain
        response = None
        result, response = self.invoke(response_chain, user_input, format)

        return result, response

    def callback(self, api):
        result = None

        # Execute the api callback function
        callbacks = import_modules_from_directory('callbacks')
        functions = {}
        for module_name, module in callbacks.items():
            functions.update({name: getattr(module, name) for name in dir(module) if callable(getattr(module, name))})

        # Use the extracted function name to retrieve and execute the function from the functions dictionary
        if api in functions:
            result = functions[api]()
        else:
            print(f"API function {api} not found in available functions.")
        return result

    def rag(self, llm, profile, prompt):
        result = True
        response = None

        # TODO: RAG
        # Query all the RAG APIs
        for obj in prompt.tools:
            if(obj["tool"] == "document_loader" and obj["loader"] == "WikipediaLoader"):
                document_loader = DocumentLoader(llm)
                resp = document_loader.WikipediaLoader(obj["query"], obj["lang"], prompt.message)
            elif(obj["tool"] == "document_loader" and obj["loader"] == "WebBaseLoader"):
                document_loader = DocumentLoader(llm)
                resp = document_loader.WebBaseLoader(obj["url"], prompt.message)
            elif(obj["tool"] == "agent" and obj["load_tools"] == "serpapi"):
                agent_tool = Agent(llm)
                resp = agent_tool.serpapi(prompt.message)
            elif(obj["tool"] == "agent" and obj["load_tools"] == "custom"):
                agent_tool = Agent(llm)
                resp = agent_tool.custom(profile, prompt)

            return True, resp

        return result, response

    def invoke(self, object, user_input, format = None):
        result = True
        response = None
        user_input = user_input + "(請用正(繁)體中文回答我)"

        try:
            response = object.invoke(user_input)
        except Exception as e:
            print(str(e))
            result = False
            return result, str(e)

        # Check the type for different objects
        try:
            if (type(object).__name__ == "ChatOpenAI"):
                response = response.content
            elif (type(object).__name__ == "HuggingFaceEndpoint"):
                response = response
            else:
                # Return the last item in the response if SequentialChain
                response = list(response.values())[-1]
        except Exception as e:
            print(str(e))
            result = False
            return result, str(e)

        if (format == "html"):
            response = format_html(response)

        return result, response