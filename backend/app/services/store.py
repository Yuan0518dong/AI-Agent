import sqlite3
import json
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "ai_agent.db"


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        conn.execute(
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
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                goal_id TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                date TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'normal',
                done INTEGER NOT NULL DEFAULT 0,
                completed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS checkins (
                id TEXT PRIMARY KEY,
                goal_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                date TEXT NOT NULL,
                status TEXT NOT NULL,
                checked_at TEXT NOT NULL,
                FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
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


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def list_goals() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM goals ORDER BY created_at DESC").fetchall()
    return [_goal_from_row(row) for row in rows]


def create_goal(goal: dict) -> dict:
    with get_connection() as conn:
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
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
    return _goal_from_row(row) if row else None


def update_goal(goal_id: str, changes: dict) -> dict | None:
    if not changes:
        return get_goal(goal_id)

    assignments = ", ".join(f"{key} = ?" for key in changes)
    values = list(changes.values())
    values.append(goal_id)

    with get_connection() as conn:
        conn.execute(f"UPDATE goals SET {assignments} WHERE id = ?", values)

    return get_goal(goal_id)


def delete_goal(goal_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
    return cursor.rowcount > 0


def create_task(task: dict) -> dict:
    db_task = {**task, "done": 1 if task["done"] else 0}

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO tasks (
                id, goal_id, title, detail, date, priority, done, completed_at, created_at, updated_at
            ) VALUES (
                :id, :goal_id, :title, :detail, :date, :priority, :done, :completed_at, :created_at, :updated_at
            )
            """,
            db_task,
        )
    return task


def get_task(task_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _task_from_row(row) if row else None


def list_tasks_for_goal(goal_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE goal_id = ? ORDER BY date, created_at",
            (goal_id,),
        ).fetchall()
    return [_task_from_row(row) for row in rows]


def list_tasks_for_date(target_date: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE date = ? ORDER BY created_at",
            (target_date,),
        ).fetchall()
    return [_task_from_row(row) for row in rows]


def update_task_checkin(task_id: str, done: bool, completed_at: str | None) -> dict | None:
    now = now_iso()

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE tasks
            SET done = ?, completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (1 if done else 0, completed_at, now, task_id),
        )

    return get_task(task_id)


def delete_tasks_for_goal(goal_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM tasks WHERE goal_id = ?", (goal_id,))


def create_checkin(checkin: dict) -> dict:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO checkins (
                id, goal_id, task_id, date, status, checked_at
            ) VALUES (
                :id, :goal_id, :task_id, :date, :status, :checked_at
            )
            """,
            checkin,
        )
    return checkin


def list_materials(goal_id: str | None = None) -> list[dict]:
    with get_connection() as conn:
        if goal_id:
            rows = conn.execute(
                "SELECT * FROM materials WHERE goal_id = ? ORDER BY created_at DESC",
                (goal_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM materials ORDER BY created_at DESC"
            ).fetchall()
    return [_material_from_row(row) for row in rows]


def create_material(material: dict) -> dict:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO materials (
                id, goal_id, title, type, content, url, created_at, updated_at
            ) VALUES (
                :id, :goal_id, :title, :type, :content, :url, :created_at, :updated_at
            )
            """,
            material,
        )
    return _material_from_mapping(material)


def get_material(material_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM materials WHERE id = ?", (material_id,)).fetchone()
    return _material_from_row(row) if row else None


def update_material(material_id: str, changes: dict) -> dict | None:
    if not changes:
        return get_material(material_id)

    assignments = ", ".join(f"{key} = ?" for key in changes)
    values = list(changes.values())
    values.append(material_id)

    with get_connection() as conn:
        conn.execute(f"UPDATE materials SET {assignments} WHERE id = ?", values)

    return get_material(material_id)


def delete_material(material_id: str) -> bool:
    with get_connection() as conn:
        _delete_material_children(conn, material_id)
        cursor = conn.execute("DELETE FROM materials WHERE id = ?", (material_id,))
    return cursor.rowcount > 0


def upsert_material_summary(summary: dict) -> dict:
    db_summary = _summary_to_db(summary)
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT material_id FROM material_summaries WHERE material_id = ?",
            (summary["material_id"],),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE material_summaries
                SET overview = :overview,
                    key_points = :key_points,
                    difficulties = :difficulties,
                    study_order = :study_order,
                    action_items = :action_items,
                    ai_mode = :ai_mode,
                    updated_at = :updated_at
                WHERE material_id = :material_id
                """,
                db_summary,
            )
        else:
            conn.execute(
                """
                INSERT INTO material_summaries (
                    material_id, overview, key_points, difficulties, study_order,
                    action_items, ai_mode, created_at, updated_at
                ) VALUES (
                    :material_id, :overview, :key_points, :difficulties, :study_order,
                    :action_items, :ai_mode, :created_at, :updated_at
                )
                """,
                db_summary,
            )

    return get_material_summary(summary["material_id"])


def get_material_summary(material_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM material_summaries WHERE material_id = ?",
            (material_id,),
        ).fetchone()
    return _summary_from_row(row) if row else None


def replace_flashcards_for_material(material_id: str, flashcards: list[dict]) -> list[dict]:
    with get_connection() as conn:
        conn.execute("DELETE FROM flashcards WHERE material_id = ?", (material_id,))
        conn.executemany(
            """
            INSERT INTO flashcards (
                id, material_id, front, back, status, created_at, updated_at
            ) VALUES (
                :id, :material_id, :front, :back, :status, :created_at, :updated_at
            )
            """,
            flashcards,
        )
    return list_flashcards_for_material(material_id)


def list_flashcards_for_material(material_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM flashcards WHERE material_id = ? ORDER BY created_at, id",
            (material_id,),
        ).fetchall()
    return [_flashcard_from_row(row) for row in rows]


def replace_quiz_questions_for_material(material_id: str, questions: list[dict]) -> list[dict]:
    db_questions = [_quiz_question_to_db(question) for question in questions]
    with get_connection() as conn:
        conn.execute("DELETE FROM quiz_questions WHERE material_id = ?", (material_id,))
        conn.executemany(
            """
            INSERT INTO quiz_questions (
                id, material_id, question, type, options, answer, explanation, created_at, updated_at
            ) VALUES (
                :id, :material_id, :question, :type, :options, :answer, :explanation, :created_at, :updated_at
            )
            """,
            db_questions,
        )
    return list_quiz_questions_for_material(material_id)


def list_quiz_questions_for_material(material_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM quiz_questions WHERE material_id = ? ORDER BY created_at, id",
            (material_id,),
        ).fetchall()
    return [_quiz_question_from_row(row) for row in rows]


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_iso() -> str:
    return date.today().isoformat()


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


def _material_from_row(row: sqlite3.Row) -> dict:
    return _material_from_mapping(dict(row))


def _material_from_mapping(material: dict) -> dict:
    return {
        "id": material["id"],
        "goalId": material["goal_id"],
        "title": material["title"],
        "type": material["type"],
        "content": material["content"],
        "url": material["url"],
        "createdAt": material["created_at"],
        "updatedAt": material["updated_at"],
    }


def _summary_to_db(summary: dict) -> dict:
    return {
        **summary,
        "key_points": json.dumps(summary["key_points"], ensure_ascii=False),
        "difficulties": json.dumps(summary["difficulties"], ensure_ascii=False),
        "study_order": json.dumps(summary["study_order"], ensure_ascii=False),
        "action_items": json.dumps(summary["action_items"], ensure_ascii=False),
    }


def _summary_from_row(row: sqlite3.Row) -> dict:
    return {
        "materialId": row["material_id"],
        "overview": row["overview"],
        "keyPoints": json.loads(row["key_points"]),
        "difficulties": json.loads(row["difficulties"]),
        "studyOrder": json.loads(row["study_order"]),
        "actionItems": json.loads(row["action_items"]),
        "aiMode": row["ai_mode"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _flashcard_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "materialId": row["material_id"],
        "front": row["front"],
        "back": row["back"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _quiz_question_to_db(question: dict) -> dict:
    return {
        **question,
        "options": json.dumps(question["options"], ensure_ascii=False),
    }


def _quiz_question_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "materialId": row["material_id"],
        "question": row["question"],
        "type": row["type"],
        "options": json.loads(row["options"]),
        "answer": row["answer"],
        "explanation": row["explanation"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _delete_material_children(conn: sqlite3.Connection, material_id: str) -> None:
    child_tables = ("material_summaries", "flashcards", "quiz_questions")
    existing_tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN (?, ?, ?)",
            child_tables,
        ).fetchall()
    }

    for table in child_tables:
        if table in existing_tables:
            conn.execute(f"DELETE FROM {table} WHERE material_id = ?", (material_id,))

