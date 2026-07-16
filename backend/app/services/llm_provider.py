import os
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any

from backend.app.services import model_usage_service
from typing import Protocol


@dataclass(frozen=True)
class LLMAnswerContext:
    question: str
    goal: dict | None
    material_id: str | None
    references: list[dict]


@dataclass(frozen=True)
class LLMAnswer:
    answer: str
    basis: str
    suggestion: str
    source_title: str
    is_from_material: bool
    confidence: str
    mode: str
    next_action: str = "answer_only"
    requires_confirmation: bool = False
    insufficiency_reason: str = ""
    review_drafts: list[dict] = field(default_factory=list)


class LLMProvider(Protocol):
    mode: str

    def generate_answer(self, context: LLMAnswerContext) -> LLMAnswer:
        ...


class MockLLMProvider:
    mode = "mock"

    def generate_answer(self, context: LLMAnswerContext) -> LLMAnswer:
        if not context.references:
            return LLMAnswer(
                answer="当前资料不足以直接回答这个问题。我不会把没有依据的内容当成资料结论。",
                basis="没有检索到与问题明显相关的资料片段。",
                suggestion=_build_fallback_suggestion(context.goal),
                source_title="",
                is_from_material=False,
                confidence="low",
                mode=self.mode,
                next_action="ask_for_more_material",
                requires_confirmation=False,
                insufficiency_reason="没有检索到与问题明显相关的资料片段。",
                review_drafts=[],
            )

        context_preview = "；".join(reference["content"] for reference in context.references)
        confidence = _estimate_confidence(context.references)
        answer_text = f"我先根据已检索到的资料片段回答：{context_preview}"
        suggestion = _build_material_suggestion(context.goal)
        return LLMAnswer(
            answer=answer_text,
            basis=_build_basis(context.references),
            suggestion=suggestion,
            source_title=context.references[0]["materialTitle"],
            is_from_material=True,
            confidence=confidence,
            mode=self.mode,
            next_action=_decide_next_action(confidence, True),
            requires_confirmation=True,
            insufficiency_reason="",
            review_drafts=_build_review_drafts(context, answer_text, suggestion, confidence),
        )


class OpenAICompatibleLLMProvider:
    mode = "openai-compatible"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 20,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.fallback_provider = MockLLMProvider()

    def generate_answer(self, context: LLMAnswerContext) -> LLMAnswer:
        if not context.references:
            return self.fallback_provider.generate_answer(context)

        try:
            result = self._post_chat_completion(_build_openai_payload(context, self.model))
            content = result["choices"][0]["message"]["content"]
            data = _parse_model_json(content)
            return _answer_from_model_data(data, context, self.mode)
        except (KeyError, TypeError, ValueError, urllib.error.URLError, TimeoutError):
            return self.fallback_provider.generate_answer(context)

    def _post_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        model_usage_service.consume_llm_call()
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


def get_llm_provider() -> LLMProvider:
    _load_env_file()
    provider_name = os.getenv("LLM_PROVIDER", "mock").strip().lower()
    if provider_name == "mock":
        return MockLLMProvider()
    if provider_name in {"zhipu", "zhipuai", "bigmodel"}:
        api_key = os.getenv("ZHIPU_API_KEY", "").strip() or os.getenv("LLM_API_KEY", "").strip()
        model = os.getenv("ZHIPU_MODEL", "").strip() or os.getenv("LLM_MODEL", "glm-4-flash").strip()
        base_url = (
            os.getenv("ZHIPU_BASE_URL", "").strip()
            or os.getenv("LLM_BASE_URL", "https://api.z.ai/api/paas/v4").strip()
        )
        timeout_seconds = _read_timeout_seconds()
        if api_key and model:
            return OpenAICompatibleLLMProvider(
                api_key=api_key,
                base_url=base_url,
                model=model,
                timeout_seconds=timeout_seconds,
            )
    if provider_name in {"openai-compatible", "openai"}:
        api_key = os.getenv("LLM_API_KEY", "").strip()
        model = os.getenv("LLM_MODEL", "").strip()
        base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").strip()
        timeout_seconds = _read_timeout_seconds()
        if api_key and model:
            return OpenAICompatibleLLMProvider(
                api_key=api_key,
                base_url=base_url,
                model=model,
                timeout_seconds=timeout_seconds,
            )

    return MockLLMProvider()


def _load_env_file(path: Path | None = None) -> None:
    configured_path = os.getenv("LLM_ENV_FILE", "").strip()
    if path or configured_path:
        env_paths = [path or Path(configured_path)]
    else:
        service_path = Path(__file__).resolve()
        env_paths = [
            service_path.parents[3] / ".env",
            service_path.parents[2] / ".env",
        ]

    for env_path in env_paths:
        if not env_path.exists():
            continue

        for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip().lstrip("\ufeff")
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _read_timeout_seconds() -> float:
    try:
        timeout_seconds = float(os.getenv("LLM_TIMEOUT_SECONDS", "20"))
    except ValueError:
        return 20
    if timeout_seconds <= 0:
        return 20
    return timeout_seconds


def _build_basis(references: list[dict]) -> str:
    titles = []
    for reference in references:
        if reference["materialTitle"] not in titles:
            titles.append(reference["materialTitle"])
    return f"依据已检索到的 {len(references)} 个资料片段，来源资料：{'、'.join(titles)}。"


def _build_material_suggestion(goal: dict | None) -> str:
    if not goal:
        return "建议先复述命中的资料片段，再补充一个练习或测试题检查理解。"

    return (
        f"结合你的目标“{goal['name']}”（{goal['subject']}，当前水平：{goal['level']}），"
        f"建议今天用 {goal['daily_minutes']} 分钟先复述资料依据，再整理 1 个待复习问题。"
    )


def _build_fallback_suggestion(goal: dict | None) -> str:
    if not goal:
        return "建议补充更相关的资料，或先为已有资料生成 chunks 后再提问。"

    return (
        f"建议围绕目标“{goal['name']}”补充与问题直接相关的资料，"
        "再重新生成 chunks 后提问。以上只是通用学习建议，不是来自当前资料。"
    )


def _estimate_confidence(references: list[dict]) -> str:
    semantic_scores = [
        reference["score"]
        for reference in references
        if reference.get("searchMode") == "semantic"
    ]
    if semantic_scores and max(semantic_scores) >= 0.55:
        return "high"
    keyword_scores = [
        reference["score"]
        for reference in references
        if reference.get("searchMode", "keyword") == "keyword"
    ]
    if keyword_scores and max(keyword_scores) >= 3:
        return "high"
    return "medium"


def _build_openai_payload(context: LLMAnswerContext, model: str) -> dict[str, Any]:
    references_text = "\n".join(
        (
            f"- 资料：{reference['materialTitle']}；片段 {reference['chunkIndex'] + 1}；"
            f"score={reference['score']}；内容：{reference['content']}"
        )
        for reference in context.references
    )
    goal_text = "无"
    if context.goal:
        goal_text = (
            f"{context.goal['name']}；方向：{context.goal['subject']}；"
            f"当前水平：{context.goal['level']}；每日时间：{context.goal['daily_minutes']} 分钟"
        )

    return {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一个学习助手。请优先且严格基于给定资料片段回答。"
                    "如果资料不足，必须明确说明资料不足，不能把通用经验说成资料结论。"
                    "只输出 JSON，不要输出 Markdown。JSON 字段必须包含："
                    "answer, basis, suggestion, isFromMaterial, confidence, nextAction, "
                    "requiresConfirmation, insufficiencyReason, reviewDrafts。"
                    "confidence 只能是 high、medium 或 low。"
                    "nextAction 只能是 answer_only、review_material、create_flashcards、"
                    "create_quiz、ask_for_more_material。"
                    "如果生成 reviewDrafts，requiresConfirmation 必须为 true。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"用户目标：{goal_text}\n"
                    f"用户问题：{context.question}\n"
                    f"资料片段：\n{references_text}\n"
                    "请给出适合学习者理解的简洁回答。"
                ),
            },
        ],
    }


def _parse_model_json(content: str) -> dict[str, Any]:
    normalized = content.strip()
    if normalized.startswith("```"):
        normalized = normalized.strip("`").removeprefix("json").strip()

    try:
        return json.loads(normalized)
    except json.JSONDecodeError:
        start = normalized.find("{")
        end = normalized.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(normalized[start : end + 1])


def _answer_from_model_data(
    data: dict[str, Any],
    context: LLMAnswerContext,
    mode: str,
) -> LLMAnswer:
    answer_text = str(data.get("answer") or "当前资料不足以直接回答这个问题。")
    basis_text = str(data.get("basis") or _build_basis(context.references))
    suggestion_text = str(data.get("suggestion") or _build_material_suggestion(context.goal))
    confidence = str(data.get("confidence") or "").lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = _estimate_confidence(context.references)

    is_from_material = data.get("isFromMaterial")
    if not isinstance(is_from_material, bool):
        is_from_material = confidence != "low"
    next_action = _normalize_next_action(data.get("nextAction"))
    requires_confirmation = data.get("requiresConfirmation")
    if not isinstance(requires_confirmation, bool):
        requires_confirmation = False
    insufficiency_reason = str(data.get("insufficiencyReason") or "")
    review_drafts = _normalize_review_drafts(data.get("reviewDrafts"))
    missing_terms = _missing_question_terms_from_references(context)
    if missing_terms and not _looks_material_insufficient(answer_text, basis_text):
        terms = "、".join(missing_terms)
        answer_text = f"当前资料不足以直接回答这个问题：资料片段中未提及 {terms}。"
        basis_text = f"给定资料片段中未检索到这些问题关键词：{terms}。"
        suggestion_text = f"建议补充包含 {terms} 的相关资料，再重新生成 chunks 后提问。"
        insufficiency_reason = f"资料片段中未提及 {terms}。"

    if (
        context.references
        and not missing_terms
        and _is_current_material_summary_question(context.question)
        and (confidence == "low" or _looks_material_insufficient(answer_text, basis_text))
    ):
        answer_text = _build_grounded_summary_answer(context)
        basis_text = _build_basis(context.references)
        suggestion_text = _build_material_suggestion(context.goal)
        confidence = "medium"
        is_from_material = True
        next_action = "review_material"
        insufficiency_reason = ""

    if confidence == "low" or missing_terms or _looks_material_insufficient(answer_text, basis_text):
        confidence = "low"
        is_from_material = False
        next_action = "ask_for_more_material"
        requires_confirmation = False
        review_drafts = []
        if not insufficiency_reason:
            insufficiency_reason = "当前资料不足以支撑这个问题的可靠回答。"
    else:
        if next_action == "answer_only":
            next_action = _decide_next_action(confidence, bool(context.references))
        if not review_drafts:
            review_drafts = _build_review_drafts(context, answer_text, suggestion_text, confidence)
        requires_confirmation = bool(review_drafts)

    return LLMAnswer(
        answer=answer_text,
        basis=basis_text,
        suggestion=suggestion_text,
        source_title=context.references[0]["materialTitle"] if context.references else "",
        is_from_material=is_from_material,
        confidence=confidence,
        mode=mode,
        next_action=next_action,
        requires_confirmation=requires_confirmation,
        insufficiency_reason=insufficiency_reason,
        review_drafts=review_drafts,
    )


def _looks_material_insufficient(answer: str, basis: str) -> bool:
    text = f"{answer}\n{basis}".lower()
    markers = [
        "资料不足",
        "未提及",
        "不涉及",
        "没有说明",
        "无法回答",
        "不能回答",
        "not discuss",
        "does not discuss",
        "insufficient",
    ]
    return any(marker in text for marker in markers)


def _is_current_material_summary_question(question: str) -> bool:
    normalized = re.sub(r"\s+", "", question or "").lower()
    markers = [
        "这份资料",
        "当前资料",
        "本文",
        "这篇",
        "这首",
        "核心内容",
        "主要内容",
        "总结",
        "概括",
        "解释这份",
        "基于资料",
        "复习建议",
        "下一步",
    ]
    return any(re.sub(r"\s+", "", marker).lower() in normalized for marker in markers)


def _build_grounded_summary_answer(context: LLMAnswerContext) -> str:
    title = context.references[0]["materialTitle"] if context.references else "当前资料"
    evidence = "；".join(reference["content"] for reference in context.references[:3])
    return (
        f"可以基于《{title}》的已检索片段先做资料内总结：{evidence}。"
        "这份资料适合先抓住核心意象或关键词，再用自己的话复述其主要内容。"
    )


def _missing_question_terms_from_references(context: LLMAnswerContext) -> list[str]:
    reference_text = " ".join(reference["content"] for reference in context.references).lower()
    ignored_terms = {
        "how",
        "what",
        "when",
        "where",
        "which",
        "why",
        "does",
        "with",
        "from",
        "this",
        "that",
        "system",
        "work",
        "works",
        "implement",
        "implementation",
    }
    terms = []
    for term in re.findall(r"[A-Za-z][A-Za-z0-9.+#-]{2,}", context.question):
        normalized = term.lower()
        if normalized in ignored_terms or normalized in reference_text:
            continue
        if term not in terms:
            terms.append(term)
    return terms[:3]


def _normalize_next_action(value: Any) -> str:
    allowed = {
        "answer_only",
        "review_material",
        "create_flashcards",
        "create_quiz",
        "ask_for_more_material",
    }
    normalized = str(value or "").strip()
    return normalized if normalized in allowed else "answer_only"


def _decide_next_action(confidence: str, has_references: bool) -> str:
    if not has_references or confidence == "low":
        return "ask_for_more_material"
    if confidence == "high":
        return "create_flashcards"
    return "review_material"


def _build_review_drafts(
    context: LLMAnswerContext,
    answer: str,
    suggestion: str,
    confidence: str,
) -> list[dict]:
    if not context.references or confidence == "low":
        return []

    if confidence == "high":
        return [
            {
                "type": "flashcard",
                "front": f"请复述：{context.question}",
                "back": _truncate(answer, 180),
                "source": "agent_qa",
            }
        ]

    return [
        {
            "type": "review_point",
            "point": _truncate(suggestion, 180),
            "source": "agent_qa",
        }
    ]


def _normalize_review_drafts(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    drafts = []
    for item in value:
        if isinstance(item, dict):
            draft_type = str(item.get("type") or "").strip()
            if draft_type in {"flashcard", "review_point", "quiz"}:
                drafts.append(item)
    return drafts[:3]


def _truncate(text: str, limit: int) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1]}…"
