import json
import re
from typing import Any

from backend.app.services import llm_provider


def summarize_material(material: dict) -> dict:
    fallback = _fallback_summary(material)
    data = _generate_summary_json(material)
    overview = _pick_text(data, ("overview", "summary", "abstract"), fallback["overview"])
    key_points = _pick_list(data, ("keyPoints", "key_points", "knowledgePoints", "knowledge_points"))
    difficulties = _pick_list(data, ("difficulties", "hardPoints", "hard_points", "possibleDifficulties"))
    study_order = _pick_list(data, ("studyOrder", "study_order", "learningOrder", "learning_order"))
    action_items = _pick_list(data, ("actionItems", "action_items", "actions", "nextActions"))
    has_ai_summary = bool(data) and any([overview != fallback["overview"], key_points, difficulties])

    return {
        "overview": overview[:240],
        "keyPoints": _normalize_list(key_points, fallback["keyPoints"], 3, 8, 120),
        "difficulties": _normalize_list(difficulties, fallback["difficulties"], 2, 5, 180),
        "studyOrder": _normalize_list(study_order, fallback["studyOrder"], 2, 5, 180),
        "actionItems": _normalize_list(action_items, fallback["actionItems"], 2, 5, 180),
        "aiMode": _result_mode(data, fallback, has_ai_summary),
    }


def _fallback_summary(material: dict) -> dict:
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


def _generate_summary_json(material: dict) -> dict[str, Any]:
    provider = llm_provider.get_llm_provider()
    if not isinstance(provider, llm_provider.OpenAICompatibleLLMProvider):
        return {}

    content = material["content"] or material["url"] or material["title"]
    payload = {
        "model": provider.model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一个面向学习者的资料整理助手。只输出 JSON，不要输出 Markdown。"
                    "只能依据用户提供的资料标题和正文整理，不要补充资料中没有出现的作者、朝代、背景或外部常识。"
                    "JSON 字段必须包含 overview, keyPoints, difficulties, studyOrder, actionItems。"
                    "overview 是 1-2 句话摘要；keyPoints 是 3-8 个关键知识点；"
                    "difficulties 是 2-5 个真正可能卡住的理解难点，必须解释为什么难，不能简单重复原句；"
                    "studyOrder 是学习顺序；actionItems 是可执行复习动作。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "title": material["title"],
                        "type": material["type"],
                        "content": content[:3000],
                        "rules": [
                            "如果资料是中文，请用中文回答。",
                            "不要把原文逐句切开当作总结。",
                            "可能难点要体现理解障碍，例如意象、背景、概念关系、易混点或答题误区。",
                            "每一项都要短而具体，适合放到学习工作台。",
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }

    try:
        result = provider._post_chat_completion(payload)
        content = result["choices"][0]["message"]["content"]
        parsed = llm_provider._parse_model_json(content)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


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


def _normalize_list(
    value: Any,
    fallback: list[str],
    min_items: int,
    max_items: int,
    max_length: int,
) -> list[str]:
    if not isinstance(value, list):
        value = []

    normalized = []
    for item in value:
        text = _text(item, "")
        if text:
            normalized.append(text[:max_length])
        if len(normalized) >= max_items:
            break

    if len(normalized) < min_items:
        normalized.extend(fallback[len(normalized) : max_items])

    return normalized[:max_items]


def _pick_text(data: dict[str, Any], keys: tuple[str, ...], fallback: str) -> str:
    for key in keys:
        if key in data:
            return _text(data.get(key), fallback)
    return fallback


def _pick_list(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in data:
            return data.get(key)
    return []


def _text(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _result_mode(data: dict[str, Any], fallback: dict, has_ai_summary: bool) -> str:
    if data and has_ai_summary:
        return str(data.get("mode") or data.get("provider") or llm_provider.get_llm_provider().mode)
    return str(fallback.get("aiMode") or "mock")
