import os
import pygsheets
import importlib.util
from langchain_openai import ChatOpenAI
from LLM.utils.gdrive import initialize_drive_service, list_files_in_drive_folder
from LLM.utils.gsheet import write_to_cell, extract_profile_from_sheet

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

class DigitalTwins:
    def __init__(self):
        self.llm = ChatOpenAI(model = "gpt-4")
        self.templates_profile = """你是{name}，{description}。"""
        self.api_intent = None
        self.api_table = None
        self.templates_intent = """請根據用戶的訊息，回傳一個API意圖。注意:
        1. 你只能回答在 {api_intent} 中的選項。
        2. 如果你不知道答案，請回答"無法識別"。
        """

        self.service = initialize_drive_service(os.getenv("CREDENTIALS_FILE"))
        self.api_table = {}

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

    def prompt_llm_twins(self, role, desrtption, prompt, api_table):
        # 定義 SDGs 的問題
        self.templates_profile = self.templates_profile.format(name = role, description = desrtption)
        question = "我想請教您一些問題。" + prompt

        # Get intent from api_table
        self.api_intent = api_table
        result, str_api = self.intent_recognition(question)

        # 呼叫 callback 函數
        if (result == False):
            return False, "無法識別"
        else:
            return True, self.callback(str_api)

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

    def intent_recognition(self, name, user_input):
        result = True
        response = None

        # Get API table
        api_table = self.load_API_table(name)
        self.templates_intent = self.templates_intent.format(api_intent = api_table)
        response = self.llm.invoke(self.templates_intent + user_input)

        return result, response

    def callback(self, api):
        result = None

        # Execute the api callback function
        callbacks = import_modules_from_directory('callbacks')
        functions = {}
        for module_name, module in callbacks.items():
            functions.update({name: getattr(module, name) for name in dir(module) if callable(getattr(module, name))})

        # 使用提取的函數名從 functions 字典中獲取函數並執行
        if api in functions:
            result = functions[api]()
        else:
            print(f"API function {api} not found in available functions.")

        return result