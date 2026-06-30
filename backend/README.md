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

## Current State

This backend uses in-memory storage only. Data will reset when the server restarts.

Next step is to replace `backend/app/services/store.py` with a real database layer.

