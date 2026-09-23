"""Validate iOS share input and durably deduplicate imports in SQLite."""

import datetime
import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert

from app.models import Article, Task

X_HOSTS = {"x.com", "www.x.com", "mobile.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"}
WECHAT_HOSTS = {"mp.weixin.qq.com"}
URL_PATTERN = re.compile(r"https?://[^\s<>\"'，。；！？]+", re.IGNORECASE)
POST_PATH = re.compile(r"/(?:([A-Za-z0-9_]+)/status(?:es)?|i/web/status)/(\d+)(?:/(?:photo|video)/\d+)?/?$")
ARTICLE_PATH = re.compile(r"/i/article/(\d+)/?$")
WECHAT_SHORT_PATH = re.compile(r"/s/([A-Za-z0-9_-]+)/?$")
WECHAT_TRACKING_QUERY_KEYS = {
    "scene", "srcid", "subscene", "sessionid", "clicktime", "enterid", "from", "chksm",
    "mpshare", "sharer_shareinfo", "sharer_shareinfo_first", "share_token", "timestamp",
    "acctmode", "pass_ticket", "frommsgid", "fromtimeline", "isappinstalled", "nettype",
}
WECHAT_STABLE_QUERY_KEYS = ("__biz", "mid", "idx", "sn")


def x_link_identity(value: str):
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme not in {"https", "http"} or parsed.hostname not in X_HOSTS:
            return None
        if parsed.username or parsed.password or parsed.port not in {None, 80, 443}:
            return None
    except ValueError:
        return None
    article = ARTICLE_PATH.fullmatch(parsed.path)
    if article:
        return f"article:{article[1]}", f"https://x.com/i/article/{article[1]}"
    post = POST_PATH.fullmatch(parsed.path)
    if post:
        author = post[1].lower() if post[1] else "i/web"
        return f"post:{post[2]}", f"https://x.com/{author}/status/{post[2]}"
    return None


def wechat_link_identity(value: str):
    try:
        parsed = urlsplit(value.strip())
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"https", "http"} or host not in WECHAT_HOSTS:
            return None
        if parsed.username or parsed.password or parsed.port not in {None, 80, 443}:
            return None
    except ValueError:
        return None

    path = parsed.path.rstrip("/") or parsed.path
    short = WECHAT_SHORT_PATH.fullmatch(parsed.path)
    if short:
        return f"wechat:path:{short[1]}", f"https://mp.weixin.qq.com/s/{short[1]}"

    if path != "/s":
        return None

    pairs = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=False) if k not in WECHAT_TRACKING_QUERY_KEYS]
    stable = {key: value for key, value in pairs if key in WECHAT_STABLE_QUERY_KEYS and value}
    if all(stable.get(key) for key in WECHAT_STABLE_QUERY_KEYS):
        query = urlencode([(key, stable[key]) for key in WECHAT_STABLE_QUERY_KEYS])
        identity = ":".join(stable[key] for key in WECHAT_STABLE_QUERY_KEYS)
        return f"wechat:query:{identity}", f"https://mp.weixin.qq.com/s?{query}"

    if not pairs:
        return None
    query = urlencode(sorted(pairs))
    return f"wechat:fallback:{path}?{query}", f"https://mp.weixin.qq.com{path}?{query}"


def shared_link_identity(value: str):
    candidate = value.rstrip(".,;:!?)]}）】»”")
    return x_link_identity(candidate) or wechat_link_identity(candidate)


def extract_shared_url(*values: str) -> tuple[str, str]:
    links = {}
    for value in values:
        for candidate in URL_PATTERN.findall(value or ""):
            identity = shared_link_identity(candidate)
            if identity:
                links.setdefault(identity[0], identity[1])
    if not links:
        raise ValueError("没有找到有效的 X 或微信文章链接。请分享具体文章，或粘贴完整链接。")
    if len(links) > 1:
        raise ValueError("收到多个不同的文章链接，请每次只分享一篇文章。")
    return next(iter(links.items()))


def task_result(task: Task, reused: bool) -> dict:
    return {
        "task_id": task.id, "status": task.status, "current_step": task.current_step,
        "original_url": task.original_url, "article_id": task.article_id,
        "created_at": task.created_at.isoformat(), "reused": reused,
    }


async def prepare_shared_task(db, identity: str, url: str, retry: bool = False):
    articles = await db.execute(select(Article))
    for article in articles.scalars():
        existing = shared_link_identity(article.original_url)
        if existing and existing[0] == identity:
            return {"status": "completed", "article_id": article.id,
                    "original_url": article.original_url, "reused": True}, False

    active = await db.execute(select(Task).where(Task.status.in_(["pending", "processing"])))
    for task in active.scalars():
        existing = shared_link_identity(task.original_url)
        if existing and existing[0] == identity:
            return task_result(task, True), False

    # A stable primary key makes duplicate submissions safe across tabs/workers.
    task_id = "share-" + hashlib.sha256(identity.encode()).hexdigest()[:32]
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    values = dict(id=task_id, original_url=url, status="pending", current_step="已收到 iPhone 分享，准备抓取…", created_at=now)
    result = await db.execute(insert(Task).values(**values).on_conflict_do_nothing(index_elements=["id"]))
    scheduled = result.rowcount == 1
    if not scheduled and retry:
        result = await db.execute(update(Task).where(Task.id == task_id, Task.status == "failed").values(
            **{key: value for key, value in values.items() if key != "id"}, error_message=None, article_id=None,
        ))
        scheduled = result.rowcount == 1
    await db.commit()
    task = await db.get(Task, task_id, populate_existing=True)
    return task_result(task, not scheduled), scheduled
