import json
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from database import initDB, selectFromDB, \
    deleteFromDB, listFromDB, \
    insertOrUpdateProfile, insertOrUpdateAPITable
from models import regUser, getUser, prompt
from LLM.LLMTwins import DigitalTwins

# Load environment variables from .env file
load_dotenv()
app = FastAPI()

# Initialize database
conn, cursor = initDB()

# Health Check
@app.get("/health")
async def health():
    return {"result": "Healthy Server!"}

@app.post("/register_llm_twins")
async def register_llm_twins(user: regUser):
    # Check if user is already registered
    result = selectFromDB(conn, "llm_twins", "name", user.name)

    # Register or update digital twins
    dt = DigitalTwins()
    result, profile, api_table = dt.register_llm_twins(user.name, user.description)

    # Insert or update profile
    if (result == True):
        result = insertOrUpdateProfile(conn, "llm_twins", "name", user.name, profile)

    # Insert or update API table
    if (result == True):
        result = insertOrUpdateAPITable(conn, "llm_twins_api", "name", user.name, api_table)

    # Return Profile & API Table
    profile["api_table"]  = api_table
    return profile

# Get LLM Digital Twins with User ID
@app.post("/get_llm_twins")
async def get_llm_twins(user: getUser):
    result = selectFromDB(conn, "llm_twins", "name", user.name)

    # Check if result is None
    if result is None:
        # Return 404 response
        raise HTTPException(status_code = 404, detail = "Digital Twin for this user is not registered")

    # TODO
    # Document loader
    # Agent
    # RAG

    return {"result": result}

# Get Digital Twins API table
@app.post("/get_llm_twins_api")
async def get_llm_twins_api(user: getUser):
    result = selectFromDB(conn, "llm_twins_api", "name", user.name)

    # Check if result is None
    if result is None:
        # Return 404 response
        raise HTTPException(status_code = 404, detail = "Digital Twin for this user is not registered")

    return {"result": json.loads(result[1])}

# Delete LLM Digital Twins with User ID
@app.post("/delete_llm_twins")
async def delete_llm_twins(user: getUser):
    result = deleteFromDB(conn, "llm_twins", "name", user.name)

    # Check if result is False
    if result == False:
        # Return 404 response
        raise HTTPException(status_code = 404, detail = "Digital Twin for this user is not registered")

    return {"message": "Digital Twin for this user has been deleted"}

# List all LLM Digital Twins
@app.get("/list_llm_twins")
async def list_llm_twins():
    result = listFromDB(conn, "llm_twins")

    return {"result": result}

# Intent recognition
@app.post("/intent_recognition")
async def intent_recognition(prompt: prompt):
    result = False

    # Get user from database
    profile = selectFromDB(conn, "llm_twins", "name", prompt.role)

    if profile is None:
        raise HTTPException(status_code = 404, detail = "Digital Twin for this user is not registered")

    # Get intent from database
    api_table = selectFromDB(conn, "llm_twins_api", "name", prompt.role)

    if api_table is None:
        raise HTTPException(status_code = 404, detail = "API table for this user is not registered")

    dt = DigitalTwins()
    result, message = dt.intent_recognition(prompt.role, prompt.message)

    return {"result": result, "message": message}

@app.post("/callbacks")
async def callbacks(prompt: prompt):
    # Get user from database
    profile = selectFromDB(conn, "llm_twins", "name", prompt.role)

    if profile is None:
        raise HTTPException(status_code = 404, detail = "Digital Twin for this user is not registered")

    # Run callback function
    dt = DigitalTwins()
    result = dt.callback(prompt.message)

    return {"result": result}