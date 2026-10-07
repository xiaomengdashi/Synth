"""相关文章推荐:纯只读查询,不动表结构。

同分类候选 + 字符 bigram 重合度打分,中文免分词;SQLite 本地读 30 行量级,不缓存。
"""

import datetime
from typing import Any, Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Article

# 候选窗口:同分类最新 30 篇,个人站规模下足够;库大了可调,本期固定值
CANDIDATE_WINDOW = 30
RELATED_FIELDS = (
    "id", "title", "summary", "source_type", "category",
    "cover_image_url", "account_name", "publish_time", "created_at",
)
# 打分+投影恰好只需这九列(不含 content_md):候选每行省掉数百 KB 的微信复刻正文
_RELATED_COLUMNS = (
    Article.id, Article.title, Article.summary, Article.source_type,
    Article.category, Article.cover_image_url, Article.account_name,
    Article.publish_time, Article.created_at,
)


def char_bigrams(text: str, limit: int = 600) -> set[str]:
    """相邻字符对集合:去空白、lower 后两两取对并去重;limit 截断防超长摘要撑爆集合。"""
    compact = "".join(text.split()).lower()[:limit]
    return {compact[i:i + 2] for i in range(len(compact) - 1)}


def _bigram_overlap(a: set[str], b: set[str]) -> float:
    """重合率 = 交集 / max(min(两边大小), 1):min 归一避免短标题吃亏,下限 1 防 0 分母。"""
    if not a or not b:
        return 0.0
    return len(a & b) / max(min(len(a), len(b)), 1)


def build_related(article: Any, candidates: Sequence[Any], limit: int = 5) -> list[Any]:
    """打分排序:2.0 同分类 + 3.0 标题重合率 + 1.0 摘要重合率;排除自身;并列按 created_at 新者先。

    article/candidates 接受 ORM 实体或多列查询行,只需鸭子类型的 id/title/summary/category/created_at。
    created_at 可空:datetime.min 只作比较哨兵(比较安全,只有 .timestamp() 会因 year 0 崩),
    排序键直接比 datetime 而非换算时间戳。
    """
    title_grams = char_bigrams(article.title or "")
    summary_grams = char_bigrams(article.summary or "")
    category = (article.category or "").strip()
    scored: list[tuple[float, datetime.datetime, Any]] = []
    for cand in candidates:
        if cand.id == article.id:
            continue
        score = 0.0
        # 同分类判定用归一后分类值(strip+空归未分类),与候选查询口径一致
        if (cand.category or "").strip() == category:
            score += 2.0
        score += 3.0 * _bigram_overlap(title_grams, char_bigrams(cand.title or ""))
        score += 1.0 * _bigram_overlap(summary_grams, char_bigrams(cand.summary or ""))
        scored.append((score, cand.created_at or datetime.datetime.min, cand))
    # 元组降序:分数高者先,并列时 created_at 新者先(NULL 哨兵最旧垫底)
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [cand for _, _, cand in scored[:limit]]


def _category_filter(article: Any):
    """同分类过滤:可空列必须显式处理 NULL——直接 == '' 会漏掉 NULL 行,直接 == None 生成
    category IS NULL 之外永不匹配的旧式比较;空值归未分类池(NULL 或空串)。"""
    value = (article.category or "").strip()
    if value:
        return func.trim(Article.category) == value
    return or_(Article.category.is_(None), Article.category == "")


async def fetch_related(db: AsyncSession, article_id: str, limit: int = 5) -> list[dict] | None:
    """取相关文章:同分类最新 30 篇候选,不足 limit 用全局最新补位;未知 id 返回 None。"""
    article = (await db.execute(
        select(*_RELATED_COLUMNS).where(Article.id == article_id)
    )).first()
    if article is None:
        return None
    candidates = list((await db.execute(
        select(*_RELATED_COLUMNS)
        .where(_category_filter(article), Article.id != article_id)
        .order_by(Article.created_at.desc())
        .limit(CANDIDATE_WINDOW)
    )).all())
    if len(candidates) < limit:
        # 补位排除自身与已入选候选,按最新补齐到 limit 篇
        picked_ids = {cand.id for cand in candidates} | {article_id}
        candidates.extend((await db.execute(
            select(*_RELATED_COLUMNS)
            .where(Article.id.not_in(picked_ids))
            .order_by(Article.created_at.desc())
            .limit(limit - len(candidates))
        )).all())
    return [
        {field: getattr(item, field) for field in RELATED_FIELDS}
        for item in build_related(article, candidates, limit=limit)
    ]
