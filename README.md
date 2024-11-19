# LLMTwins
https://docs.phidata.com/agents/introduction

## Environment

#### Environment Variables:
- CREDENTIALS_FILE: Google service account private key JSON
- GDRIVE_LLM_ROOT_PATH: LLM root path on Google Drive
- GSHEET_FOR_TEMPLATE_OF_LLM_PROFILE: Template ID for Google sheet
- OPENAI_API_KEY (Optional): OpenAI API Key

## Installation
```bash=
python3.10 -m venv env
source env/bin/active
pip3 install -r requirements.txt
```

## Run
```bash=
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

#### LLM Profile:
- [Profile on GoogleSheet (Template)](https://docs.google.com/spreadsheets/d/1OpWdGNPZSW-782J9zmLW3vT5hIUyQaX2XNotjJB0AD0/edit?usp=sharing)
