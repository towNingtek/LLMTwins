import os
from langchain_openai import ChatOpenAI
from langchain_community.llms import HuggingFaceEndpoint
from LLM.utils.format import format_html
from LLM.utils.RAG.agent import Agent

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
