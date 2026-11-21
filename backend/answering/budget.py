"""Независимый от retrieval бюджет полного входа Answer."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AnswerBudget:
    # Рабочие настройки, не измеренный оптимум качества/стоимости.
    max_input_tokens: int = 32_000
    max_output_tokens: int = 4_096
    context_tokens: int = 128_000
    safety_tokens: int = 2_048

    def __post_init__(self):
        for name in ("max_input_tokens", "max_output_tokens", "context_tokens", "safety_tokens"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} должен быть положительным целым числом")
        if self.max_input_tokens + self.max_output_tokens + self.safety_tokens > self.context_tokens:
            raise ValueError("Бюджет Answer с ответом и запасом превышает окно модели")


DEFAULT_ANSWER_BUDGET = AnswerBudget()


class InputBudgetExceeded(ValueError):
    """Полный запрос не помещается; не означает отсутствие сведений в корпусе."""

    def __init__(self, stage: str, tokens: int, limit: int):
        self.stage, self.tokens, self.limit = stage, tokens, limit
        super().__init__(f"Вход {stage}: {tokens} токенов, бюджет {limit}")
