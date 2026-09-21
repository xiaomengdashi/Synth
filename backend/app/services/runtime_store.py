TASKS_DB: dict[str, dict] = {}
ARTICLES_DB: dict[str, dict] = {}


def update_task(task_id: str, **updates) -> None:
    task = TASKS_DB.get(task_id)
    if not task:
        return
    task.update(updates)


def task_created_at(task_data: dict) -> str:
    return task_data["created_at"]


def article_from_db_record(article) -> dict:
    return {
        "id": article.id,
        "title": article.title,
        "summary": article.summary,
        "content_md": article.content_md,
        "original_url": article.original_url,
        "source_type": article.source_type,
        "cover_image_url": article.cover_image_url,
        "created_at": article.created_at.isoformat() if article.created_at else "",
    }
