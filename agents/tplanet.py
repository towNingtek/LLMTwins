import json
import requests
from langchain.agents import tool

API_ENDPOINT_TPLANET = "https://tplanet-backend.townway.com.tw"
SITE_OWNER_OF_EDU_FIELD = "david@damaie.com.tw"
URL_PROJECT_CONTENT = "https://beyondschool.damaie.com.tw/content.html?uuid="

@tool
def get_edu_dataframe(str_obj):
    """Get data about education."""
    payload = {'email': SITE_OWNER_OF_EDU_FIELD}
        
    # First conversion from JSON string to dictionary
    obj = None
    try:
        obj = json.loads(str_obj)
        
        # Second conversion if the first conversion results in a string
        if isinstance(obj, str):
            obj = json.loads(obj)
    except json.JSONDecodeError as e:
        print("JSON decode error:", e)
        return "Invalid JSON input"
    
    # Ensure obj is a dictionary
    if not isinstance(obj, dict):
        return "Invalid JSON input: Expected a dictionary"
    
    # Filter by weight of the project
    list_project = []
    try:
        response = requests.request("POST", f"{API_ENDPOINT_TPLANET}/projects/projects", data=payload)
        response.raise_for_status()
        projects = response.json().get("projects", [])
        for item in projects:
            response_project_info = requests.request("GET", f"{API_ENDPOINT_TPLANET}/projects/info/{item}")
            response_project_info.raise_for_status()
            obj_project = json.loads(response_project_info.text)
            if "uuid" in obj_project:
                list_project.append(item)
    except requests.RequestException as e:
        print("Request error:", e)
        return "Failed to fetch project data"
    
    # Re-format to HTML
    list_response = []
    response = "這些計畫一共是"
    if "format" in obj and obj["format"] == "html":
        for project_item in list_project:
            project_link = f"{URL_PROJECT_CONTENT}{project_item}"
            project_html = f"<a href='{project_link}'>{project_item}</a>"
            list_response.append(project_html)
        
        for project_html in list_response:
            response += project_html + "<br>"
    else:
        for project_item in list_project:
            project_link = f"{URL_PROJECT_CONTENT}{project_item}，\n"
            list_response.append(project_link)
        
        for project_link in list_response:
            response += project_link + ","
    
    response += "，請點擊連結查看詳細資訊。"
    return response
