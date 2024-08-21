from fastapi import FastAPI
from dotenv import load_dotenv
from models import prompt
from LLM.LLMTwins import DigitalTwins
from fastapi.middleware.cors import CORSMiddleware

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

# Intent recognition
@app.post("/prompt")
async def prompt(prompt: prompt):
    result = False
    message = ""

    # Set model from prompt
    dt = DigitalTwins()
    dt.set_model(prompt.model if prompt.model is not None else None)

    result, message = dt.prompt("me", prompt)
    return {"result": result, "message": message}
