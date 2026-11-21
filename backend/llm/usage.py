"""Суммирование фактического usage GigaChat без оценки отсутствующих данных."""

TOKEN_FIELDS = ("prompt_tokens", "completion_tokens", "precached_prompt_tokens", "total_tokens")


def summarize_usage(calls: list[dict]) -> dict:
    """Суммы API и покрытие по каждому полю; неизвестное не считается нулём."""
    totals = {}
    coverage = {}
    for field in TOKEN_FIELDS:
        values = [
            call["usage"][field] for call in calls
            if isinstance(call.get("usage"), dict)
            and type(call["usage"].get(field)) is int and call["usage"][field] >= 0
        ]
        totals[field] = sum(values) if values else None
        coverage[field] = len(values)
    return {
        "calls": len(calls), "tokens": totals, "calls_with_field": coverage,
        "complete": all(count == len(calls) for count in coverage.values()),
    }
