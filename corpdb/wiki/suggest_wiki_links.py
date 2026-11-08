"""Поиск кандидатов и предложения направленных Wiki-связей без сохранения."""

from corpdb.wiki.evaluate_wiki_pair import evaluate_wiki_pair
from corpdb.wiki.find_wiki_candidates import find_wiki_candidates


def suggest_wiki_links(
    page_id: int,
    *,
    hits_per_chunk: int = 10,
    max_candidates: int = 20,
    evidence_per_candidate: int = 2,
    max_input_chars: int = 60_000,
) -> dict:
    """Оценивает каждого кандидата один раз в порядке поисковой выдачи.

    links содержит только положительные решения с явными source/target ID.
    evaluations сохраняет также отказы с пояснениями; retrieval — основания
    поиска, лимиты и статистику. Ошибка любой пары прерывает операцию без
    частичного результата. Уже выполненные вызовы LLM при этом не отменяются.
    Существующие связи не читаются и не изменяются.
    """
    if type(page_id) is not int or page_id <= 0:
        raise ValueError("ID Wiki должен быть положительным целым числом")
    if type(max_input_chars) is not int or max_input_chars <= 0:
        raise ValueError("max_input_chars должен быть положительным целым числом")
    retrieval = find_wiki_candidates(
        page_id,
        hits_per_chunk=hits_per_chunk,
        max_candidates=max_candidates,
        evidence_per_candidate=evidence_per_candidate,
    )
    evaluations = []
    links = []
    for candidate in retrieval["candidates"]:
        target_id = candidate["page_id"]
        evaluation = evaluate_wiki_pair(page_id, target_id, max_input_chars=max_input_chars)
        evaluations.append(evaluation)
        for direction, source, target in (
            ("a_to_b", page_id, target_id),
            ("b_to_a", target_id, page_id),
        ):
            decision = evaluation[direction]
            if decision["create"]:
                links.append({
                    "source_page_id": source,
                    "target_page_id": target,
                    "explanation": decision["explanation"],
                })
    return {
        "source_page_id": page_id,
        "links": links,
        "evaluations": evaluations,
        "retrieval": retrieval,
    }
