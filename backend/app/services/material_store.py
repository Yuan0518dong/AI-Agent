import json
import sqlite3
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DB_PATH = DATA_DIR / "ai_agent.db"


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = OFF")
        if _schema_needs_rebuild(conn):
            _drop_tables(conn)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS materials (
                id TEXT PRIMARY KEY,
                goal_id TEXT,
                title TEXT NOT NULL,
                type TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

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
            );

            CREATE TABLE IF NOT EXISTS flashcards (
                id TEXT PRIMARY KEY,
                material_id TEXT NOT NULL,
                front TEXT NOT NULL,
                back TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE
            );

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
            );
            """
        )


def clear_material_data() -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM quiz_questions")
        conn.execute("DELETE FROM flashcards")
        conn.execute("DELETE FROM material_summaries")
        conn.execute("DELETE FROM materials")


def list_materials(goal_id: str | None = None) -> list[dict]:
    with _connect() as conn:
        if goal_id:
            rows = conn.execute(
                """
                SELECT * FROM materials
                WHERE goal_id = ?
                ORDER BY created_at ASC
                """,
                (goal_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM materials ORDER BY created_at ASC").fetchall()
    return [_material_from_row(row) for row in rows]


def get_material(material_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM materials WHERE id = ?",
            (material_id,),
        ).fetchone()
    return _material_from_row(row) if row else None


def save_material(material: dict) -> dict:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO materials (
                id, goal_id, title, type, content, url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                goal_id = excluded.goal_id,
                title = excluded.title,
                type = excluded.type,
                content = excluded.content,
                url = excluded.url,
                updated_at = excluded.updated_at
            """,
            (
                material["id"],
                material["goalId"],
                material["title"],
                material["type"],
                material["content"],
                material["url"],
                material["createdAt"],
                material["updatedAt"],
            ),
        )
    return get_material(material["id"]) or material


def delete_material(material_id: str) -> bool:
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM materials WHERE id = ?", (material_id,))
    return cursor.rowcount > 0


def get_material_summary(material_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM material_summaries WHERE material_id = ?",
            (material_id,),
        ).fetchone()
    return _summary_from_row(row) if row else None


def save_material_summary(material_id: str, summary: dict) -> dict:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO material_summaries (
                material_id, overview, key_points, difficulties, study_order, action_items,
                ai_mode, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(material_id) DO UPDATE SET
                overview = excluded.overview,
                key_points = excluded.key_points,
                difficulties = excluded.difficulties,
                study_order = excluded.study_order,
                action_items = excluded.action_items,
                ai_mode = excluded.ai_mode,
                updated_at = excluded.updated_at
            """,
            (
                material_id,
                summary["overview"],
                json.dumps(summary["keyPoints"], ensure_ascii=False),
                json.dumps(summary["difficulties"], ensure_ascii=False),
                json.dumps(summary["studyOrder"], ensure_ascii=False),
                json.dumps(summary["actionItems"], ensure_ascii=False),
                summary["aiMode"],
                summary["createdAt"],
                summary["updatedAt"],
            ),
        )
    return get_material_summary(material_id) or summary


def list_flashcards_for_material(material_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM flashcards
            WHERE material_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (material_id,),
        ).fetchall()
    return [_flashcard_from_row(row) for row in rows]


def replace_flashcards_for_material(
    material_id: str,
    next_flashcards: list[dict],
) -> list[dict]:
    with _connect() as conn:
        conn.execute("DELETE FROM flashcards WHERE material_id = ?", (material_id,))
        conn.executemany(
            """
            INSERT INTO flashcards (
                id, material_id, front, back, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    flashcard["id"],
                    flashcard["materialId"],
                    flashcard["front"],
                    flashcard["back"],
                    flashcard["status"],
                    flashcard["createdAt"],
                    flashcard["updatedAt"],
                )
                for flashcard in next_flashcards
            ],
        )
    return list_flashcards_for_material(material_id)


def list_quiz_questions_for_material(material_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM quiz_questions
            WHERE material_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (material_id,),
        ).fetchall()
    return [_quiz_question_from_row(row) for row in rows]


def replace_quiz_questions_for_material(
    material_id: str,
    next_questions: list[dict],
) -> list[dict]:
    with _connect() as conn:
        conn.execute("DELETE FROM quiz_questions WHERE material_id = ?", (material_id,))
        conn.executemany(
            """
            INSERT INTO quiz_questions (
                id, material_id, question, type, options, answer, explanation, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    question["id"],
                    question["materialId"],
                    question["question"],
                    question["type"],
                    json.dumps(question["options"], ensure_ascii=False),
                    question["answer"],
                    question["explanation"],
                    question["createdAt"],
                    question["updatedAt"],
                )
                for question in next_questions
            ],
        )
    return list_quiz_questions_for_material(material_id)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _schema_needs_rebuild(conn: sqlite3.Connection) -> bool:
    material_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'materials'"
    ).fetchone()
    if not material_row:
        return False

    material_foreign_keys = conn.execute("PRAGMA foreign_key_list(materials)").fetchall()
    if material_foreign_keys:
        return True

    summary_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(material_summaries)").fetchall()
    }
    expected_summary_columns = {
        "difficulties",
        "study_order",
        "action_items",
    }
    return bool(summary_columns) and not expected_summary_columns.issubset(summary_columns)


def _drop_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS quiz_questions;
        DROP TABLE IF EXISTS flashcards;
        DROP TABLE IF EXISTS material_summaries;
        DROP TABLE IF EXISTS materials;
        """
    )


def _material_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "goalId": row["goal_id"],
        "title": row["title"],
        "type": row["type"],
        "content": row["content"],
        "url": row["url"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
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


init_db()
