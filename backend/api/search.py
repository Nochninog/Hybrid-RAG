"""Обработка вопроса штатной цепочкой retrieval → Explore → SelectDocs → Answer."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from backend.api.common import create_app, operation
from backend.workflows.explore import answer_question

app = create_app("search-service")


class QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]
    limit: int = Field(default=10, strict=True, ge=1, le=100)
    max_depth: int = Field(default=2, strict=True, ge=0, le=10)
    max_expansions: int = Field(default=20, strict=True, ge=1, le=100)


@app.post("/questions")
def ask(request: QuestionRequest):
    with operation("answer_question"):
        result = answer_question(**request.model_dump())
    # Внешнему клиенту не нужны полные промпты и тексты всех кандидатов.
    fields = ("answer", "sources", "missing_parts", "budget_missing_parts",
              "explore_status", "explore_error")
    return {key: result[key] for key in fields}
