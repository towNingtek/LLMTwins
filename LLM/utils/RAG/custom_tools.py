import os
import json
import requests
from langchain.agents import tool

@tool
def device_info(text: str) -> str:
    """Return the device info."""
    url = os.getenv("API_END_POINT_PECULAB") + "/api/states/switch.mqtt_ntnu_1_2_sw_2"

    payload = ""
    headers = {
        'Content-type': 'application/json ',
        'Authorization': 'Bearer ' + os.environ.get("API_KEY_PECULAB")
    }

    response = requests.request("GET", url, headers = headers, data = payload)

    return json.dumps(response.text)

@tool
def device_on(text: str) -> str:
    """Trun on the A device."""
    url = os.getenv("API_END_POINT_PECULAB") + "/api/webhook/-TJO7MQn5u--KlqSH4Mw2JHA7"

    payload = ""
    headers = {
        'Content-type': 'application/json ',
        'Authorization': 'Bearer ' + os.environ.get("API_KEY_PECULAB")
    }

    response = requests.request("POST", url, headers = headers, data = payload)

    if (response.status_code == 200):
        print("Device is on")

    return json.dumps(response.text)

@tool
def device_off(text: str) -> str:
    """Trun off the A device."""
    url = os.getenv("API_END_POINT_PECULAB") + "/api/webhook/-jAxX99jM2ghu4SVD29Ht8Flx"

    payload = ""
    headers = {
        'Content-type': 'application/json ',
        'Authorization': 'Bearer ' + os.environ.get("API_KEY_PECULAB")
    }

    response = requests.request("POST", url, headers = headers, data = payload)

    if (response.status_code == 200):
        print("Device is off")

    return json.dumps(response.text)