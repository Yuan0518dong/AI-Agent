"""Single write path for FSRS-backed flashcards."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fsrs import Card, Rating, Scheduler

from backend.app.services import material_store, store


SCHEDULER = Scheduler(
    desired_retention=0.9,
    maximum_interval=365,
    enable_fuzzing=False,
)
RATINGS = {
    "again": Rating.Again,
    "hard": Rating.Hard,
    "good": Rating.Good,
    "easy": Rating.Easy,
}
STATUS_BY_RATING = {
    "again": "review",
    "hard": "review",
    "good": "known",
    "easy": "known",
}


class FlashcardScheduleError(ValueError):
    """A persisted FSRS schedule cannot be safely read or updated."""


class FlashcardStatusResetError(ValueError):
    """A legacy status update attempted to erase completed review history."""


def new_scheduled_flashcard(
    *,
    material_id: str,
    front: str,
    back: str,
    flashcard_id: str | None = None,
    now: datetime | str | None = None,
) -> dict:
    """Create an immediately due, UTC FSRS card without inventing history."""
    front_text = _required_text({"front": front}, "front")
    back_text = _required_text({"back": back}, "back")
    created_at = _as_utc_datetime(now)
    fsrs_card = Card(due=created_at)
    return {
        "id": flashcard_id or store.make_id("flashcard"),
        "materialId": material_id,
        "front": front_text,
        "back": back_text,
        "status": "new",
        "fsrsCard": fsrs_card.to_json(),
        "dueAt": _iso_utc(fsrs_card.due),
        "lastReviewedAt": None,
        "reviewCount": 0,
        "lastRating": None,
        "createdAt": _iso_utc(created_at),
        "updatedAt": _iso_utc(created_at),
    }


def normalize_scheduled_flashcard(flashcard: dict) -> dict:
    """Preserve a complete schedule, or initialize legacy input immediately due."""
    required_schedule_fields = {
        "fsrsCard",
        "dueAt",
        "lastReviewedAt",
        "reviewCount",
        "lastRating",
    }
    if required_schedule_fields <= flashcard.keys():
        normalized = dict(flashcard)
        normalized["front"] = _required_text(normalized, "front")
        normalized["back"] = _required_text(normalized, "back")
        if not isinstance(normalized.get("status"), str):
            raise ValueError("Flashcard status must be a string.")
        _load_schedule(normalized)
        return normalized

    return new_scheduled_flashcard(
        material_id=_required_text(flashcard, "materialId"),
        front=_required_text(flashcard, "front"),
        back=_required_text(flashcard, "back"),
        flashcard_id=flashcard.get("id"),
        now=flashcard.get("createdAt") or flashcard.get("updatedAt"),
    )


def create_flashcard_for_material(flashcard: dict) -> dict:
    scheduled = normalize_scheduled_flashcard(flashcard)
    with store.db_connection() as conn:
        insert_scheduled_flashcard(conn, scheduled)
    return scheduled


def replace_flashcards_for_material(material_id: str, flashcards: list[dict]) -> list[dict]:
    scheduled_cards = [normalize_scheduled_flashcard(card) for card in flashcards]
    if any(card["materialId"] != material_id for card in scheduled_cards):
        raise ValueError("Every flashcard must belong to the replacement material.")

    with store.db_connection() as conn:
        conn.execute("DELETE FROM flashcards WHERE material_id = ?", (material_id,))
        for card in scheduled_cards:
            insert_scheduled_flashcard(conn, card)
    return scheduled_cards


def insert_scheduled_flashcard(conn, flashcard: dict) -> None:
    """Insert one already-built schedule into the caller's transaction."""
    scheduled = normalize_scheduled_flashcard(flashcard)
    conn.execute(
        """
        INSERT INTO flashcards (
            id, material_id, front, back, status, fsrs_card, due_at,
            last_reviewed_at, review_count, last_rating, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            scheduled["id"],
            scheduled["materialId"],
            scheduled["front"],
            scheduled["back"],
            scheduled["status"],
            scheduled["fsrsCard"],
            scheduled["dueAt"],
            scheduled["lastReviewedAt"],
            scheduled["reviewCount"],
            scheduled["lastRating"],
            scheduled["createdAt"],
            scheduled["updatedAt"],
        ),
    )


def review_flashcard(material_id: str, flashcard_id: str, rating: str) -> dict | None:
    rating_name = rating.strip().lower()
    if rating_name not in RATINGS:
        raise ValueError("rating must be again, hard, good, or easy")

    reviewed_at = datetime.now(timezone.utc)
    with store.db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM flashcards WHERE id = ? AND material_id = ?",
            (flashcard_id, material_id),
        ).fetchone()
        if not row:
            return None
        flashcard = material_store._flashcard_from_row(row)
        fsrs_card = _load_schedule(flashcard)
        next_fsrs_card, _ = SCHEDULER.review_card(
            fsrs_card,
            RATINGS[rating_name],
            review_datetime=reviewed_at,
        )
        updated = {
            **flashcard,
            "status": STATUS_BY_RATING[rating_name],
            "fsrsCard": next_fsrs_card.to_json(),
            "dueAt": _iso_utc(next_fsrs_card.due),
            "lastReviewedAt": _iso_utc(next_fsrs_card.last_review),
            "reviewCount": int(flashcard["reviewCount"]) + 1,
            "lastRating": rating_name,
            "updatedAt": _iso_utc(reviewed_at),
        }
        _load_schedule(updated)
        conn.execute(
            """
            UPDATE flashcards
            SET status = ?, fsrs_card = ?, due_at = ?, last_reviewed_at = ?,
                review_count = ?, last_rating = ?, updated_at = ?
            WHERE id = ? AND material_id = ?
            """,
            (
                updated["status"],
                updated["fsrsCard"],
                updated["dueAt"],
                updated["lastReviewedAt"],
                updated["reviewCount"],
                updated["lastRating"],
                updated["updatedAt"],
                flashcard_id,
                material_id,
            ),
        )
    return updated


def apply_legacy_status(material_id: str, flashcard_id: str, status: str) -> dict | None:
    """Map historical status mutations to the corresponding FSRS rating."""
    normalized_status = status.strip().lower()
    if normalized_status == "known":
        return review_flashcard(material_id, flashcard_id, "good")
    if normalized_status == "review":
        return review_flashcard(material_id, flashcard_id, "again")
    if normalized_status != "new":
        raise ValueError("Invalid flashcard status")

    with store.db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM flashcards WHERE id = ? AND material_id = ?",
            (flashcard_id, material_id),
        ).fetchone()
        if not row:
            return None
        flashcard = material_store._flashcard_from_row(row)
        _load_schedule(flashcard)
        if int(flashcard["reviewCount"]) != 0:
            raise FlashcardStatusResetError("flashcard_review_history_exists")
    return flashcard


def list_due_flashcards(goal_id: str | None, user_id: str | None) -> list[dict]:
    due_before = _iso_utc(datetime.now(timezone.utc))
    clauses = ["flashcards.due_at <= ?"]
    parameters: list[Any] = [due_before]
    if goal_id is not None:
        clauses.append("materials.goal_id = ?")
        parameters.append(goal_id)
    if user_id is None:
        clauses.append("materials.user_id IS NULL")
    else:
        clauses.append("materials.user_id = ?")
        parameters.append(user_id)

    with store.db_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT flashcards.*, materials.goal_id, materials.title AS material_title
            FROM flashcards
            JOIN materials ON materials.id = flashcards.material_id
            WHERE {' AND '.join(clauses)}
            ORDER BY flashcards.due_at ASC, flashcards.id ASC
            """,
            parameters,
        ).fetchall()
    return [
        {
            **present_flashcard(material_store._flashcard_from_row(row)),
            "goalId": row["goal_id"],
            "materialTitle": row["material_title"],
        }
        for row in rows
    ]


def review_response(flashcard: dict) -> dict:
    return {
        "flashcardId": flashcard["id"],
        "status": flashcard["status"],
        "dueAt": flashcard["dueAt"],
        "lastReviewedAt": flashcard["lastReviewedAt"],
        "reviewCount": flashcard["reviewCount"],
        "lastRating": flashcard["lastRating"],
        "retrievability": _retrievability(flashcard),
    }


def present_flashcard(flashcard: dict) -> dict:
    return {**flashcard, "retrievability": _retrievability(flashcard)}


def _load_schedule(flashcard: dict) -> Card:
    try:
        fsrs_card = Card.from_json(flashcard["fsrsCard"])
        due_at = _as_utc_datetime(flashcard["dueAt"])
    except (KeyError, TypeError, ValueError) as exc:
        raise FlashcardScheduleError("flashcard_schedule_invalid") from exc
    if _iso_utc(fsrs_card.due) != _iso_utc(due_at):
        raise FlashcardScheduleError("flashcard_schedule_invalid")
    try:
        review_count = int(flashcard["reviewCount"])
        last_rating = flashcard["lastRating"]
        last_reviewed_at = flashcard["lastReviewedAt"]
        status = flashcard["status"]
    except (KeyError, TypeError, ValueError) as exc:
        raise FlashcardScheduleError("flashcard_schedule_invalid") from exc
    if review_count < 0:
        raise FlashcardScheduleError("flashcard_schedule_invalid")
    if review_count == 0:
        if status != "new" or last_rating is not None or last_reviewed_at is not None:
            raise FlashcardScheduleError("flashcard_schedule_invalid")
        if fsrs_card.last_review is not None:
            raise FlashcardScheduleError("flashcard_schedule_invalid")
        return fsrs_card
    if last_rating not in RATINGS or status != STATUS_BY_RATING[last_rating] or not last_reviewed_at:
        raise FlashcardScheduleError("flashcard_schedule_invalid")
    try:
        if _iso_utc(fsrs_card.last_review) != _iso_utc(_as_utc_datetime(last_reviewed_at)):
            raise FlashcardScheduleError("flashcard_schedule_invalid")
    except (TypeError, ValueError) as exc:
        raise FlashcardScheduleError("flashcard_schedule_invalid") from exc
    return fsrs_card


def _retrievability(flashcard: dict) -> float | None:
    fsrs_card = _load_schedule(flashcard)
    if int(flashcard["reviewCount"]) == 0:
        return None
    try:
        return SCHEDULER.get_card_retrievability(fsrs_card, datetime.now(timezone.utc))
    except ValueError:
        return None


def _required_text(values: dict, field: str) -> str:
    value = values.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Flashcard field {field} must be a non-empty string.")
    return value.strip()


def _as_utc_datetime(value: datetime | str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _as_utc_datetime(value).isoformat()
