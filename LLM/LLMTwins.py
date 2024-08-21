import os
from langchain_openai import ChatOpenAI
from langchain_community.llms import HuggingFaceEndpoint
from langchain.callbacks.base import BaseCallbackHandler
from LLM.utils.format import format_html
from LLM.utils.module_handler import import_modules_from_directory
from LLM.utils.RAG.agent import Agent

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

    def set_model(self, model = None):
        if (model == None):
            self.llm = ChatOpenAI(model = "gpt-4o", temperature = 0)
        else:
            print(f"Model is set to {model}.")
            self.llm = HuggingFaceEndpoint(repo_id = model, huggingfacehub_api_token = os.getenv("HUGGINGFACEHUB_API_TOKEN"))

    def prompt(self, profile, prompt):
        result = True
        response = None

        if (prompt.type == "RAG"):
            result, response = self.rag(self.llm, profile, prompt)

        return result, response

    def rag(self, llm, profile, prompt):
        result = True
        response = None
        for obj in prompt.tools:
            if(obj["tool"] == "agent" and obj["load_tools"] == "custom"):
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
