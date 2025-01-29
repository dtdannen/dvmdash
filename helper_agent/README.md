# Helper Agent to Assist with Easy Issues

This is an openhands agent that runs on a digital ocean droplet to automatically attempt to fix github issues. 

## Installation

Follow the instructions here:

https://github.com/All-Hands-AI/OpenHands/blob/main/openhands/resolver/README.md

1. Create a new github account for the agent (or use your own, except it will look like you are fixing all the issues)
2. Add a .env file here with the github token, LLM, and LLM API Key

```
GITHUB_TOKEN="your-github-token"
GITHUB_USERNAME="your-github-username"
LLM_MODEL="anthropic/claude-3-5-sonnet-20241022"  # Recommended
LLM_API_KEY="your-llm-api-key"
```

3. Create a virtual env and install the requirements
4. Install docker
4. Run main.py
