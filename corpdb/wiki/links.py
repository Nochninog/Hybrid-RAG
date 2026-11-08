from corpdb.database.insert_wiki_link import insert_wiki_link


def save_wiki_link(
    source_page_id: int,
    target_page_id: int,
    explanation: str,
) -> None:
    if source_page_id == target_page_id:
        raise ValueError("Нельзя создать ссылку Wiki-страницы на себя")
    clean_explanation = explanation.strip()

    if not clean_explanation:
        raise ValueError("Нет пояснения связи")

    insert_wiki_link(
        source_page_id=source_page_id,
        target_page_id=target_page_id,
        explanation=clean_explanation,
    )
