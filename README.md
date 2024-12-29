# LLMTwins
https://docs.phidata.com/agents/introduction

## Environment

#### Environment Variables:
- OPENAI_API_KEY: OpenAI API Key

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