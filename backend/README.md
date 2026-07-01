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
python -m pip install -r backend/requirements.txt
```

Start API server from project root:

```bash
python -m uvicorn backend.app.main:app --reload
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

This backend uses SQLite for local persistence.

The local database file is created automatically at:

```text
backend/data/ai_agent.db
```

The database file is ignored by Git. It is for local development only.

Next step is to connect the frontend prototype to these APIs.
