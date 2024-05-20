import os
import json
import requests
from langchain.agents import load_tools
from langchain.agents import initialize_agent
from langchain.agents import AgentType
from langchain.agents import tool

@tool
def device_info(text: str) -> str:
    """Return today's temperature."""
    url = os.getenv("API_END_POINT_PECULAB")

    payload = ""
    headers = {
        'Content-type': 'application/json ',
        'Authorization': 'Bearer ' + os.environ.get("API_KEY_PECULAB")
    }

    response = requests.request("GET", url, headers = headers, data = payload)

    return json.dumps(response.text)

class Agent():
    def __init__(self, llm):
        self.llm = llm

    def serpapi(self, message):
        tools = load_tools(["serpapi"], llm = self.llm)
        agent = initialize_agent(tools, self.llm, agent = AgentType.ZERO_SHOT_REACT_DESCRIPTION, verbose = False)
        return agent.invoke(message)
    
    def custom(self, message):
        tools = load_tools([], llm = self.llm)
        agent= initialize_agent(
            tools + [device_info],
            self.llm,
            agent = AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            handle_parsing_errors = True,
            max_execution_time = 30,
            verbose = False)

        try:
            result = agent({"input": message})
            return result["output"]
        except Exception as e:
            print(str(e))
            return str(e)