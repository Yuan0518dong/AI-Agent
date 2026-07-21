from __future__ import annotations


def resolve_review_material_ids(context: dict) -> list[str]:
    """Return the deterministic, current-goal material scope for a review draft."""
    scope_goal_id = (context.get("scope") or {}).get("goalId")
    if not scope_goal_id:
        return []

    scoped_material_ids = [
        material.get("id")
        for material in context.get("materials") or []
        if material.get("id") and material.get("goalId") == scope_goal_id
    ]
    scoped_set = set(scoped_material_ids)
    weak_material_ids = [
        attempt.get("materialId")
        for attempt in (context.get("quiz") or {}).get("weakAttempts") or []
        if attempt.get("materialId") in scoped_set
    ]
    return _unique_ids(weak_material_ids or scoped_material_ids)


def _unique_ids(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    unique = []
    for value in values:
        if not isinstance(value, str) or not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique
