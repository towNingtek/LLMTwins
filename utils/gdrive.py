import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

def initialize_drive_service(credentials_file):
    credentials = service_account.Credentials.from_service_account_file(credentials_file, scopes=['https://www.googleapis.com/auth/drive'])
    drive_service = build('drive', 'v3', credentials=credentials)

    return drive_service


def list_files_in_drive_folder(service, folder_id):
    list_file_id = []
    # 調用Drive API
    results = service.files().list(
        q=f"'{folder_id}' in parents",
        fields="nextPageToken, files(id, name)").execute()
    items = results.get('files', [])
    items = sorted(items, key=lambda x: x['name'])

    if items:
        for item in items:
            list_file_id.append({"name":item['name'], "file_id":item['id']})

    return list_file_id