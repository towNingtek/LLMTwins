from fastapi import FastAPI
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from phi.agent import Agent
from phi.model.openai import OpenAIChat
from models import  prompt
import agents.小鎮賦能.query_projects
import agents.小鎮賦能.analysis_projects

# Load environment variables from .env file
load_dotenv()
app = FastAPI()

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health Check
@app.get("/health")
async def health():
    return {"result": "Healthy Server!"}

# 建立三個專門的 agent
edu_agent = Agent(
   name="Education Agent",
   role="查詢教育相關計畫",
   tools=[agents.小鎮賦能.query_projects.get_edu_dataframe],
   show_tool_calls=True
)

ocean_agent = Agent(
   name="Ocean Agent",
   role="查詢海洋相關計畫",
   tools=[agents.小鎮賦能.query_projects.get_ocean_dataframe],
   show_tool_calls=True
)

tour_agent = Agent(
   name="Tour Agent",
   role="查詢遊程相關計畫",
   tools=[agents.小鎮賦能.query_projects.get_tour_dataframe],
   show_tool_calls=True
)

analysis_project_agent = Agent(
   name="Project analysis Agent",
   role="以 SROI 分析計畫",
   tools=[agents.小鎮賦能.analysis_projects.analyse_project],
   show_tool_calls=True
)

# Create agent team
agent_team = Agent(
    model=OpenAIChat(
        id = "gpt-4o",
        temperature = 1,
        timeout = 30
    ),
   name="小鎮賦能團隊",
   team=[edu_agent, ocean_agent, tour_agent, analysis_project_agent],
   add_history_to_messages=True,
   num_history_responses=3,
   # instructions=["根據查詢內容選擇適當的agent執行任務"],
   show_tool_calls=False,
   tool_call_limit=1
)

@app.post("/prompt")
async def prompt(prompt: prompt):
    # json_params = json.dumps({"weight":["07", "12"]})
    response = agent_team.run(f"{prompt.message}", stream=False)
    # 尋找 assistant role 的最後一條訊息
    assistant_content = None
    for message in response.messages:
        if message.role == "assistant" and message.content:
            assistant_content = message.content

    return {"result": True, "message": assistant_content}