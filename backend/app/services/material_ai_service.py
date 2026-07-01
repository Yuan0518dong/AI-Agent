import re


def summarize_material(material: dict) -> dict:
    text = material["content"] or material["url"] or material["title"]
    sentences = _split_sentences(text)
    key_points = [sentence[:80] for sentence in sentences[:5]]
    if not key_points:
        key_points = ["提炼资料中的核心概念", "整理可复习的关键问题"]

    return {
        "overview": _build_overview(sentences),
        "key_points": key_points,
        "difficulties": [
            f"容易卡住：{point}。先用自己的话复述，再回到资料核对。"
            for point in key_points[:3]
        ],
        "study_order": [
            "先快速通读资料，标出不熟悉的词句。",
            f"再重点理解：{key_points[0]}。",
            "最后用闪卡和测试题检查是否能独立复述。",
        ],
        "action_items": [
            "用 3 句话写下资料摘要。",
            "完成 1 轮闪卡复习。",
            "任选 1 个知识点做简答自测。",
        ],
        "ai_mode": "mock",
    }


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
