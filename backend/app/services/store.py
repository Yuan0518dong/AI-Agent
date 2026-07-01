from datetime import date, datetime, timezone
from uuid import uuid4


goals: dict[str, dict] = {}
tasks: dict[str, dict] = {}
checkins: list[dict] = []
materials: dict[str, dict] = {}
material_summaries: dict[str, dict] = {}
flashcards: dict[str, dict] = {}
quiz_questions: dict[str, dict] = {}


def reset() -> None:
    goals.clear()
    tasks.clear()
    checkins.clear()
    materials.clear()
    material_summaries.clear()
    flashcards.clear()
    quiz_questions.clear()


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_iso() -> str:
    return date.today().isoformat()


def delete_material_children(material_id: str) -> None:
    material_summaries.pop(material_id, None)

    flashcard_ids = [
        flashcard_id
        for flashcard_id, flashcard in flashcards.items()
        if flashcard["materialId"] == material_id
    ]
    for flashcard_id in flashcard_ids:
        del flashcards[flashcard_id]

    quiz_ids = [
        quiz_id
        for quiz_id, question in quiz_questions.items()
        if question["materialId"] == material_id
    ]
    for quiz_id in quiz_ids:
        del quiz_questions[quiz_id]


def list_flashcards_for_material(material_id: str) -> list[dict]:
    return [
        flashcard
        for flashcard in flashcards.values()
        if flashcard["materialId"] == material_id
    ]


def replace_flashcards_for_material(material_id: str, next_flashcards: list[dict]) -> list[dict]:
    for flashcard in list_flashcards_for_material(material_id):
        del flashcards[flashcard["id"]]

    for flashcard in next_flashcards:
        flashcards[flashcard["id"]] = flashcard

    return list_flashcards_for_material(material_id)


def list_quiz_questions_for_material(material_id: str) -> list[dict]:
    return [
        question
        for question in quiz_questions.values()
        if question["materialId"] == material_id
    ]


def replace_quiz_questions_for_material(material_id: str, next_questions: list[dict]) -> list[dict]:
    for question in list_quiz_questions_for_material(material_id):
        del quiz_questions[question["id"]]

    for question in next_questions:
        quiz_questions[question["id"]] = question

    return list_quiz_questions_for_material(material_id)

