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
            "back": f"先用自己的话说明“{point}”，再回到资料中核对依据，并补充一个使用场景。",
        }
        for point in summary["keyPoints"]
    ]


def generate_quiz_questions(summary: dict) -> list[dict]:
    overview = summary.get("overview") or "当前资料"
    return [_build_quiz_question(point, index, overview) for index, point in enumerate(summary["keyPoints"])]


def _build_quiz_question(point: str, index: int, overview: str) -> dict:
    variants = [
        {
            "type": "short",
            "options": [],
            "question": f"用自己的话解释：{point}",
            "answer": f"答案应围绕“{point}”展开，并能说出它在资料中的作用或结论。",
            "explanation": f"这道题检查你是否真正理解了资料中的关键点，而不是只记住原句。资料摘要：{overview[:80]}",
        },
        {
            "type": "application",
            "options": [],
            "question": f"如果把“{point}”用到你的学习或项目里，第一步应该怎么做？",
            "answer": f"先找到资料中支撑“{point}”的依据，再把它转成一个可执行的小动作或复习问题。",
            "explanation": "这道题检查能不能把资料知识转成真实学习行动，贴近用户复习和实践场景。",
        },
        {
            "type": "boundary",
            "options": [],
            "question": f"判断并说明理由：学习“{point}”时，只记住结论就够了，不需要回到资料依据。",
            "answer": "不对。需要回到资料依据核对来源，否则容易把自己的猜测当成资料结论。",
            "explanation": "这道题检查资料依据意识，也对应第三版智能体的资料不足判断规则。",
        },
    ]
    return variants[index % len(variants)]


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
