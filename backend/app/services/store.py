import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

# Keep this hook when migrating goal/task storage; material data lives in material_store.
from backend.app.services import material_store

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DEFAULT_DB_PATH = DATA_DIR / "ai_agent.db"
DB_PATH = DEFAULT_DB_PATH


def set_db_path(path: str | Path | None) -> None:
    global DB_PATH
    DB_PATH = Path(path) if path else DEFAULT_DB_PATH
    init_db()
    material_store.set_db_path(DB_PATH)


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.parent != DATA_DIR:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_connection():
    conn = get_connection()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db() -> None:
    with db_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS goals (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                subject TEXT NOT NULL,
                level TEXT NOT NULL,
                deadline TEXT NOT NULL,
                daily_minutes INTEGER NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                goal_id TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT NOT NULL,
                date TEXT NOT NULL,
                priority TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                completed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS checkins (
                id TEXT PRIMARY KEY,
                goal_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                date TEXT NOT NULL,
                status TEXT NOT NULL,
                checked_at TEXT NOT NULL,
                FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS materials (
                id TEXT PRIMARY KEY,
                goal_id TEXT,
                title TEXT NOT NULL,
                type TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS material_summaries (
                material_id TEXT PRIMARY KEY,
                overview TEXT NOT NULL,
                key_points TEXT NOT NULL,
                difficulties TEXT NOT NULL,
                study_order TEXT NOT NULL,
                action_items TEXT NOT NULL,
                ai_mode TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS flashcards (
                id TEXT PRIMARY KEY,
                material_id TEXT NOT NULL,
                front TEXT NOT NULL,
                back TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quiz_questions (
                id TEXT PRIMARY KEY,
                material_id TEXT NOT NULL,
                question TEXT NOT NULL,
                type TEXT NOT NULL,
                options TEXT NOT NULL,
                answer TEXT NOT NULL,
                explanation TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE
            )
            """
        )


def reset() -> None:
    init_db()
    with db_connection() as conn:
        conn.execute("DELETE FROM checkins")
        conn.execute("DELETE FROM tasks")
        conn.execute("DELETE FROM goals")

    # Smoke tests call store.reset(), so material SQLite test data must be cleared here too.
    material_store.clear_material_data()


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_iso() -> str:
    return date.today().isoformat()


def list_goals() -> list[dict]:
    init_db()
    with db_connection() as conn:
        rows = conn.execute("SELECT * FROM goals ORDER BY created_at DESC").fetchall()
    return [_goal_from_row(row) for row in rows]


def create_goal(goal: dict) -> dict:
    init_db()
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO goals (
                id, name, subject, level, deadline, daily_minutes, notes, created_at, updated_at
            ) VALUES (
                :id, :name, :subject, :level, :deadline, :daily_minutes, :notes, :created_at, :updated_at
            )
            """,
            goal,
        )
    return goal


def get_goal(goal_id: str) -> dict | None:
    init_db()
    with db_connection() as conn:
        row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
    return _goal_from_row(row) if row else None


def update_goal(goal_id: str, changes: dict) -> dict | None:
    if not changes:
        return get_goal(goal_id)

    allowed_fields = {"name", "subject", "level", "deadline", "daily_minutes", "notes", "updated_at"}
    assignments = []
    values = []
    for key, value in changes.items():
        if key not in allowed_fields:
            continue
        assignments.append(f"{key} = ?")
        values.append(value)

    if not assignments:
        return get_goal(goal_id)

    values.append(goal_id)
    init_db()
    with db_connection() as conn:
        cursor = conn.execute(
            f"UPDATE goals SET {', '.join(assignments)} WHERE id = ?",
            values,
        )
        if cursor.rowcount == 0:
            return None
    return get_goal(goal_id)


def delete_goal(goal_id: str) -> bool:
    init_db()
    with db_connection() as conn:
        cursor = conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
    return cursor.rowcount > 0


def list_goal_tasks(goal_id: str) -> list[dict]:
    init_db()
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE goal_id = ? ORDER BY date ASC, created_at ASC",
            (goal_id,),
        ).fetchall()
    return [_task_from_row(row) for row in rows]


def list_tasks_by_date(target_date: str) -> list[dict]:
    init_db()
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE date = ? ORDER BY created_at ASC",
            (target_date,),
        ).fetchall()
    return [_task_from_row(row) for row in rows]


def create_task(task: dict) -> dict:
    init_db()
    task_for_db = {**task, "done": int(task["done"])}
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO tasks (
                id, goal_id, title, detail, date, priority, done, completed_at, created_at, updated_at
            ) VALUES (
                :id, :goal_id, :title, :detail, :date, :priority, :done, :completed_at, :created_at, :updated_at
            )
            """,
            task_for_db,
        )
    return task


def get_task(task_id: str) -> dict | None:
    init_db()
    with db_connection() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _task_from_row(row) if row else None


def delete_tasks_for_goal(goal_id: str) -> None:
    init_db()
    with db_connection() as conn:
        conn.execute("DELETE FROM tasks WHERE goal_id = ?", (goal_id,))


def set_task_checkin(task_id: str, done: bool) -> dict | None:
    task = get_task(task_id)
    if not task:
        return None

    now = now_iso()
    completed_at = now if done else None
    init_db()
    with db_connection() as conn:
        conn.execute(
            """
            UPDATE tasks
            SET done = ?, completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (int(done), completed_at, now, task_id),
        )
        conn.execute(
            """
            INSERT INTO checkins (
                id, goal_id, task_id, date, status, checked_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                make_id("checkin"),
                task["goal_id"],
                task_id,
                today_iso(),
                "completed" if done else "canceled",
                now,
            ),
        )
    return get_task(task_id)


def goal_exists(goal_id: str) -> bool:
    return get_goal(goal_id) is not None


def _goal_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "subject": row["subject"],
        "level": row["level"],
        "deadline": row["deadline"],
        "daily_minutes": row["daily_minutes"],
        "notes": row["notes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _task_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "goal_id": row["goal_id"],
        "title": row["title"],
        "detail": row["detail"],
        "date": row["date"],
        "priority": row["priority"],
        "done": bool(row["done"]),
        "completed_at": row["completed_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
