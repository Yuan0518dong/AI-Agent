import json
import math
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from backend.app.services import embedding_provider


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
                    user_id TEXT,
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
                    embedding TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS material_qa_records (
                    id TEXT PRIMARY KEY,
                    material_id TEXT NOT NULL,
                    goal_id TEXT,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    basis TEXT NOT NULL,
                    suggestion TEXT NOT NULL,
                    source_title TEXT NOT NULL,
                    is_from_material INTEGER NOT NULL,
                    confidence TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    next_action TEXT NOT NULL DEFAULT 'answer_only',
                    requires_confirmation INTEGER NOT NULL DEFAULT 0,
                    insufficiency_reason TEXT NOT NULL DEFAULT '',
                    review_drafts TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
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

                CREATE TABLE IF NOT EXISTS quiz_attempts (
                    id TEXT PRIMARY KEY,
                    quiz_id TEXT NOT NULL,
                    material_id TEXT NOT NULL,
                    user_answer TEXT NOT NULL,
                    is_correct INTEGER NOT NULL,
                    score INTEGER NOT NULL,
                    feedback TEXT NOT NULL,
                    suggestion TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (quiz_id) REFERENCES quiz_questions(id) ON DELETE CASCADE,
                    FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE
                );
                """
            )
            _ensure_columns(conn)
    finally:
        conn.close()


def clear_material_data() -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM quiz_attempts")
        conn.execute("DELETE FROM quiz_questions")
        conn.execute("DELETE FROM flashcards")
        conn.execute("DELETE FROM material_qa_records")
        conn.execute("DELETE FROM material_chunks")
        conn.execute("DELETE FROM material_summaries")
        conn.execute("DELETE FROM materials")


def list_materials(goal_id: str | None = None, user_id: str | None = None) -> list[dict]:
    filters = []
    values = []
    if goal_id:
        filters.append("goal_id = ?")
        values.append(goal_id)
    if user_id:
        filters.append("user_id = ?")
        values.append(user_id)
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM materials {where_clause} ORDER BY created_at ASC",
            values,
        ).fetchall()
    return [_material_from_row(row) for row in rows]


def get_material(material_id: str, user_id: str | None = None) -> dict | None:
    with _connect() as conn:
        if user_id:
            row = conn.execute(
                "SELECT * FROM materials WHERE id = ? AND user_id = ?",
                (material_id, user_id),
            ).fetchone()
        else:
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
                id, user_id, goal_id, title, type, content, url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                user_id = excluded.user_id,
                goal_id = excluded.goal_id,
                title = excluded.title,
                type = excluded.type,
                content = excluded.content,
                url = excluded.url,
                updated_at = excluded.updated_at
            """,
            (
                material["id"],
                material.get("userId"),
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


def delete_material(material_id: str, user_id: str | None = None) -> bool:
    with _connect() as conn:
        if user_id:
            cursor = conn.execute(
                "DELETE FROM materials WHERE id = ? AND user_id = ?",
                (material_id, user_id),
            )
        else:
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
                id, material_id, chunk_index, content, keywords, embedding, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    chunk["id"],
                    chunk["materialId"],
                    chunk["chunkIndex"],
                    chunk["content"],
                    json.dumps(chunk["keywords"], ensure_ascii=False),
                    json.dumps(chunk.get("embedding", [])),
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


def search_chunks(query: str, limit: int = 5, user_id: str | None = None) -> list[dict]:
    normalized_query = query.strip().lower()
    if not normalized_query:
        return []

    query_terms = _extract_keywords(normalized_query)
    with _connect() as conn:
        where_clause = "WHERE materials.user_id = ?" if user_id else ""
        values = (user_id,) if user_id else ()
        rows = conn.execute(
            """
            SELECT
                material_chunks.*,
                materials.title AS material_title,
                materials.goal_id AS goal_id
            FROM material_chunks
            JOIN materials ON materials.id = material_chunks.material_id
            {where_clause}
            ORDER BY material_chunks.created_at ASC, material_chunks.chunk_index ASC
            """.format(where_clause=where_clause),
            values,
        ).fetchall()

    try:
        query_embedding = embedding_provider.get_embedding_provider().embed(normalized_query)
    except Exception:
        query_embedding = []

    semantic_scored: list[tuple[float, dict]] = []
    keyword_scored: list[tuple[int, dict]] = []
    for row in rows:
        chunk = _chunk_from_row(row)
        stored_embedding = json.loads(row["embedding"] or "[]")
        haystack = " ".join(
            [
                row["material_title"],
                chunk["content"],
                " ".join(chunk["keywords"]),
            ]
        ).lower()
        score = _score_chunk(normalized_query, query_terms, haystack)
        chunk["materialTitle"] = row["material_title"]
        chunk["goalId"] = row["goal_id"]
        if query_embedding and stored_embedding:
            similarity = _cosine_similarity(query_embedding, stored_embedding)
            if similarity >= 0.35:
                semantic_chunk = {**chunk, "score": round(similarity, 6), "searchMode": "semantic"}
                semantic_scored.append((similarity, semantic_chunk))
        if score > 0:
            keyword_chunk = {**chunk, "score": score, "searchMode": "keyword"}
            keyword_scored.append((score, keyword_chunk))

    if semantic_scored:
        semantic_scored.sort(key=lambda item: item[0], reverse=True)
        results = [chunk for _, chunk in semantic_scored[:limit]]
        result_ids = {chunk["id"] for chunk in results}
        keyword_scored.sort(key=lambda item: item[0], reverse=True)
        for _, chunk in keyword_scored:
            if len(results) >= limit:
                break
            if chunk["id"] not in result_ids:
                results.append(chunk)
                result_ids.add(chunk["id"])
        return results
    keyword_scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in keyword_scored[:limit]]


def save_qa_record(record: dict) -> dict:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO material_qa_records (
                id, material_id, goal_id, question, answer, basis, suggestion, source_title,
                is_from_material, confidence, mode, next_action, requires_confirmation,
                insufficiency_reason, review_drafts, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["id"],
                record["materialId"],
                record["goalId"],
                record["question"],
                record["answer"],
                record["basis"],
                record["suggestion"],
                record["sourceTitle"],
                1 if record["isFromMaterial"] else 0,
                record["confidence"],
                record["mode"],
                record.get("nextAction", "answer_only"),
                1 if record.get("requiresConfirmation") else 0,
                record.get("insufficiencyReason", ""),
                json.dumps(record.get("reviewDrafts", []), ensure_ascii=False),
                record["createdAt"],
            ),
        )
    return record


def list_qa_records_for_material(material_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM material_qa_records
            WHERE material_id = ?
            ORDER BY created_at ASC
            """,
            (material_id,),
        ).fetchall()
    return [_qa_record_from_row(row) for row in rows]


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


def create_flashcard_for_material(flashcard: dict) -> dict:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO flashcards (
                id, material_id, front, back, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                flashcard["id"],
                flashcard["materialId"],
                flashcard["front"],
                flashcard["back"],
                flashcard["status"],
                flashcard["createdAt"],
                flashcard["updatedAt"],
            ),
        )
    return flashcard


def update_flashcard_status(material_id: str, flashcard_id: str, status: str, updated_at: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM flashcards
            WHERE id = ? AND material_id = ?
            """,
            (flashcard_id, material_id),
        ).fetchone()
        if not row:
            return None

        conn.execute(
            """
            UPDATE flashcards
            SET status = ?, updated_at = ?
            WHERE id = ? AND material_id = ?
            """,
            (status, updated_at, flashcard_id, material_id),
        )

    return get_flashcard(material_id, flashcard_id)


def get_flashcard(material_id: str, flashcard_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM flashcards
            WHERE id = ? AND material_id = ?
            """,
            (flashcard_id, material_id),
        ).fetchone()
    return _flashcard_from_row(row) if row else None


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


def get_quiz_question(material_id: str, quiz_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM quiz_questions
            WHERE id = ? AND material_id = ?
            """,
            (quiz_id, material_id),
        ).fetchone()
    return _quiz_question_from_row(row) if row else None


def save_quiz_attempt(attempt: dict) -> dict:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO quiz_attempts (
                id, quiz_id, material_id, user_answer, is_correct, score,
                feedback, suggestion, mode, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attempt["id"],
                attempt["quizId"],
                attempt["materialId"],
                attempt["userAnswer"],
                1 if attempt["isCorrect"] else 0,
                attempt["score"],
                attempt["feedback"],
                attempt["suggestion"],
                attempt["mode"],
                attempt["createdAt"],
            ),
        )
    return attempt


def list_quiz_attempts_for_material(material_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM quiz_attempts
            WHERE material_id = ?
            ORDER BY created_at DESC
            """,
            (material_id,),
        ).fetchall()
    return [_quiz_attempt_from_row(row) for row in rows]


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
    material_columns = _column_names(conn, "materials")
    if "user_id" not in material_columns:
        conn.execute("ALTER TABLE materials ADD COLUMN user_id TEXT")

    chunk_columns = _column_names(conn, "material_chunks")
    if "embedding" not in chunk_columns:
        conn.execute("ALTER TABLE material_chunks ADD COLUMN embedding TEXT NOT NULL DEFAULT '[]'")

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

    qa_columns = _column_names(conn, "material_qa_records")
    qa_defaults = {
        "next_action": "'answer_only'",
        "requires_confirmation": "0",
        "insufficiency_reason": "''",
        "review_drafts": "'[]'",
    }
    for column, default in qa_defaults.items():
        if column not in qa_columns:
            conn.execute(
                f"ALTER TABLE material_qa_records ADD COLUMN {column} TEXT NOT NULL DEFAULT {default}"
                if column != "requires_confirmation"
                else f"ALTER TABLE material_qa_records ADD COLUMN {column} INTEGER NOT NULL DEFAULT {default}"
            )


def _column_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def _material_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "userId": row["user_id"],
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


def _quiz_attempt_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "quizId": row["quiz_id"],
        "materialId": row["material_id"],
        "userAnswer": row["user_answer"],
        "isCorrect": bool(row["is_correct"]),
        "score": row["score"],
        "feedback": row["feedback"],
        "suggestion": row["suggestion"],
        "mode": row["mode"],
        "createdAt": row["created_at"],
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


def _qa_record_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "materialId": row["material_id"],
        "goalId": row["goal_id"],
        "question": row["question"],
        "answer": row["answer"],
        "basis": row["basis"],
        "suggestion": row["suggestion"],
        "sourceTitle": row["source_title"],
        "isFromMaterial": bool(row["is_from_material"]),
        "confidence": row["confidence"],
        "mode": row["mode"],
        "nextAction": row["next_action"],
        "requiresConfirmation": bool(row["requires_confirmation"]),
        "insufficiencyReason": row["insufficiency_reason"],
        "reviewDrafts": json.loads(row["review_drafts"]),
        "createdAt": row["created_at"],
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
        _append_keyword(keywords, token)
        if _is_cjk_text(token):
            for keyword in _cjk_ngrams(token):
                _append_keyword(keywords, keyword)
        if len(keywords) >= max_keywords:
            break
    return keywords


def _append_keyword(keywords: list[str], keyword: str) -> None:
    if keyword and keyword not in keywords:
        keywords.append(keyword)


def _is_cjk_text(text: str) -> bool:
    return bool(re.fullmatch(r"[\u4e00-\u9fff]+", text))


def _cjk_ngrams(text: str, min_size: int = 2, max_size: int = 4) -> list[str]:
    grams: list[str] = []
    for size in range(min_size, min(max_size, len(text)) + 1):
        for index in range(0, len(text) - size + 1):
            gram = text[index : index + size]
            if gram not in grams:
                grams.append(gram)
    return grams


def _score_chunk(query: str, query_terms: list[str], haystack: str) -> int:
    score = 0
    if query and query in haystack:
        score += 3
    for term in query_terms:
        if term in haystack:
            score += 1
    return score


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


init_db()
