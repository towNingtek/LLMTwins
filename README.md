# LLMTwins

## Overview

**LLMTwins** is a lightweight and modular framework for building AI-powered agents. It integrates seamlessly with different tools and frameworks, allowing for easy deployment and customization. Designed to be scalable and extensible, LLMTwins enables rapid development of intelligent agents for various applications.

## Environment

This project requires specific environment variables to function correctly.

#### Required Environment Variables:
- `OPENAI_API_KEY`: OpenAI API Key for accessing language models.

## Installation

```bash
# Create and activate a virtual environment
python3.10 -m venv env
source env/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Running the Server

```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

## Agent Tools

LLMTwins supports a modular agent-based approach. Agents are designed to work across multiple frameworks and can be integrated dynamically into the system. To use or extend existing agents, place them inside the appropriate framework directory before running the server.

```bash
cp -r <source-agents-directory> <target-framework-directory>/agents/
```
