import os
from dataclasses import dataclass
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
            )

        context_preview = "；".join(reference["content"] for reference in context.references)
        return LLMAnswer(
            answer=f"我先根据已检索到的资料片段回答：{context_preview}",
            basis=_build_basis(context.references),
            suggestion=_build_material_suggestion(context.goal),
            source_title=context.references[0]["materialTitle"],
            is_from_material=True,
            confidence=_estimate_confidence(context.references),
            mode=self.mode,
        )


def get_llm_provider() -> LLMProvider:
    provider_name = os.getenv("LLM_PROVIDER", "mock").strip().lower()
    if provider_name == "mock":
        return MockLLMProvider()

    # Keep a safe fallback until real providers are implemented.
    return MockLLMProvider()


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
    best_score = max(reference["score"] for reference in references)
    if best_score >= 3:
        return "high"
    return "medium"
