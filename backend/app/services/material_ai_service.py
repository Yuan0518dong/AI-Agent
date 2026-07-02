import re


def summarize_material(material: dict) -> dict:
    text = material["content"] or material["url"] or material["title"]
    sentences = _split_sentences(text)
    key_points = [sentence[:80] for sentence in sentences[:5]]
    if not key_points:
        key_points = ["提炼资料中的核心概念", "整理可复习的关键问题"]

    return {
        "overview": _build_overview(sentences),
        "keyPoints": key_points,
        "difficulties": [
            f"容易卡住：{point}。先用自己的话复述，再回到资料核对。"
            for point in key_points[:3]
        ],
        "studyOrder": [
            "先快速通读资料，标出不熟悉的词句。",
            f"再重点理解：{key_points[0]}。",
            "最后用闪卡和测试题检查是否能独立复述。",
        ],
        "actionItems": [
            "用 3 句话写下资料摘要。",
            "完成 1 轮闪卡复习。",
            "任选 1 个知识点做简答自测。",
        ],
        "aiMode": "mock",
    }


def generate_flashcards(summary: dict) -> list[dict]:
    return [
        {
            "front": f"请解释：{point}",
            "back": f"围绕“{point}”进行复述，并补充一个例子。",
        }
        for point in summary["keyPoints"]
    ]


def generate_quiz_questions(summary: dict) -> list[dict]:
    return [
        {
            "type": "short",
            "question": f"简答：{point} 的核心含义是什么？",
            "options": [],
            "answer": "先说明核心含义，再结合资料中的例子解释。",
            "explanation": f"这道题对应资料整理结果中的知识点“{point}”。",
        }
        for point in summary["keyPoints"]
    ]


def _split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    return [
        item.strip()
        for item in re.split(r"[。！？!?；;\n]", normalized)
        if len(item.strip()) > 2
    ]


def _build_overview(sentences: list[str]) -> str:
    overview = "。".join(sentences[:2]).strip()
    return overview[:160] or "这份资料已保存，可用于资料整理、记忆训练和成长问答。"
