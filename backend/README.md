# AI-Agent Backend

Python backend scaffold for the AI-Agent MVP.

Current owner scope for Chen:

```text
Goal management
Action plan tasks
Task check-in
Progress statistics
```

## Run Locally

Install dependencies:

```bash
pip install -r backend/requirements.txt
```

Start API server from project root:

```bash
uvicorn backend.app.main:app --reload
```

Open API docs:

```text
http://127.0.0.1:8000/docs
```

Run API smoke check:

```bash
python backend/smoke_api.py
```

## Current State

This backend uses SQLite storage for Chen's goal module data.

Default database path:

```text
backend/data/ai_agent.db
```

The database file is ignored by Git. Automated tests use a temporary SQLite database and will not clear local app data.

