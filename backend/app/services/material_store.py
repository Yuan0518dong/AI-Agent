import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DEFAULT_DB_PATH = DATA_DIR / "ai_agent.db"
DB_PATH = DEFAULT_DB_PATH


def set_db_path(path: str | Path | None) -> None:
    global DB_PATH
    DB_PATH = Path(path) if path else DEFAULT_DB_PATH
    init_db()


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        with conn:
            conn.execute("PRAGMA foreign_keys = ON")
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

                CREATE TABLE IF NOT EXISTS material_chunks (
                    id TEXT PRIMARY KEY,
                    material_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    keywords TEXT NOT NULL,
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
            _ensure_columns(conn)
    finally:
        conn.close()


def clear_material_data() -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM quiz_questions")
        conn.execute("DELETE FROM flashcards")
        conn.execute("DELETE FROM material_chunks")
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


def split_material_content(
    content: str,
    max_chars: int = 320,
    overlap_chars: int = 40,
) -> list[str]:
    normalized = re.sub(r"[ \t\r\f\v]+", " ", content).strip()
    if not normalized:
        return []

    parts = [
        part.strip()
        for part in re.split(r"(?<=[。！？!?；;.])|\n+", normalized)
        if part.strip()
    ]
    if not parts:
        parts = [normalized]

    chunks: list[str] = []
    current = ""
    for part in parts:
        if len(part) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_text(part, max_chars, overlap_chars))
            continue

        candidate = f"{current} {part}".strip() if current else part
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = _with_overlap(current, part, overlap_chars)

    if current:
        chunks.append(current)

    return chunks


def replace_chunks_for_material(
    material_id: str,
    chunks: list[dict],
) -> list[dict]:
    with _connect() as conn:
        conn.execute("DELETE FROM material_chunks WHERE material_id = ?", (material_id,))
        conn.executemany(
            """
            INSERT INTO material_chunks (
                id, material_id, chunk_index, content, keywords, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    chunk["id"],
                    chunk["materialId"],
                    chunk["chunkIndex"],
                    chunk["content"],
                    json.dumps(chunk["keywords"], ensure_ascii=False),
                    chunk["createdAt"],
                    chunk["updatedAt"],
                )
                for chunk in chunks
            ],
        )
    return list_chunks_for_material(material_id)


def list_chunks_for_material(material_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM material_chunks
            WHERE material_id = ?
            ORDER BY chunk_index ASC
            """,
            (material_id,),
        ).fetchall()
    return [_chunk_from_row(row) for row in rows]


def search_chunks(query: str, limit: int = 5) -> list[dict]:
    normalized_query = query.strip().lower()
    if not normalized_query:
        return []

    query_terms = _extract_keywords(normalized_query)
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                material_chunks.*,
                materials.title AS material_title,
                materials.goal_id AS goal_id
            FROM material_chunks
            JOIN materials ON materials.id = material_chunks.material_id
            ORDER BY material_chunks.created_at ASC, material_chunks.chunk_index ASC
            """
        ).fetchall()

    scored: list[tuple[int, dict]] = []
    for row in rows:
        chunk = _chunk_from_row(row)
        haystack = " ".join(
            [
                row["material_title"],
                chunk["content"],
                " ".join(chunk["keywords"]),
            ]
        ).lower()
        score = _score_chunk(normalized_query, query_terms, haystack)
        if score <= 0:
            continue
        chunk["materialTitle"] = row["material_title"]
        chunk["goalId"] = row["goal_id"]
        chunk["score"] = score
        scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored[:limit]]


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


def extract_keywords(text: str) -> list[str]:
    return _extract_keywords(text)


@contextmanager
def _connect():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _ensure_columns(conn: sqlite3.Connection) -> None:
    summary_columns = _column_names(conn, "material_summaries")
    summary_defaults = {
        "overview": "''",
        "key_points": "'[]'",
        "difficulties": "'[]'",
        "study_order": "'[]'",
        "action_items": "'[]'",
        "ai_mode": "'mock'",
        "created_at": "''",
        "updated_at": "''",
    }
    for column, default in summary_defaults.items():
        if column not in summary_columns:
            conn.execute(
                f"ALTER TABLE material_summaries ADD COLUMN {column} TEXT NOT NULL DEFAULT {default}"
            )


def _column_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


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


def _chunk_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "materialId": row["material_id"],
        "chunkIndex": row["chunk_index"],
        "content": row["content"],
        "keywords": json.loads(row["keywords"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _split_long_text(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(0, end - overlap_chars)
    return [chunk for chunk in chunks if chunk]


def _with_overlap(previous: str, next_text: str, overlap_chars: int) -> str:
    if overlap_chars <= 0:
        return next_text
    overlap = previous[-overlap_chars:].strip()
    return f"{overlap} {next_text}".strip() if overlap else next_text


def _extract_keywords(text: str, max_keywords: int = 20) -> list[str]:
    normalized = text.lower()
    tokens = re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]{2,}", normalized)
    keywords: list[str] = []
    for token in tokens:
        if token not in keywords:
            keywords.append(token)
        if len(keywords) >= max_keywords:
            break
    return keywords


def _score_chunk(query: str, query_terms: list[str], haystack: str) -> int:
    score = 0
    if query and query in haystack:
        score += 3
    for term in query_terms:
        if term in haystack:
            score += 1
    return score


init_db()
