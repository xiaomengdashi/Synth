from app.timezones import local_iso

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
        "account_name": article.account_name,
        "publish_time": article.publish_time,
        "category": article.category,
        "is_starred": article.is_starred,
        "read_progress": article.read_progress,
        "updated_at": local_iso(article.updated_at),
        "created_at": local_iso(article.created_at),
    }
