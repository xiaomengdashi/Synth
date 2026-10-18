"""文章对外输出的隐私裁剪:读者可见面只保留文章内容与展示元信息。

account_name 在邮件导入链路存的是发件人邮箱地址,直接外露会泄露白名单发件人;
email_message_id 是内部去重键,前台无消费方。列表接口走显式列 select 已天然
不含内部列,详情/导出统一经过本模块——以后 ORM 新增敏感列也不会随整行序列化外泄。
"""

import re

# 形如 local@domain 的单 token 视为邮箱地址(X 作者名/公众号名不含 @)
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EMAIL_SOURCE_LABEL = "邮件来稿"


def public_account_name(value: str | None) -> str:
    text = str(value or "").strip()
    return EMAIL_SOURCE_LABEL if _EMAIL_PATTERN.match(text) else text


# 读者级详情的字段白名单:白名单外的列(如 email_message_id)不随详情外发
PUBLIC_ARTICLE_FIELDS = (
    "id", "title", "summary", "content_md", "original_url", "source_type",
    "cover_image_url", "account_name", "publish_time", "category",
    "is_starred", "read_progress", "created_at", "updated_at",
)


def public_article_payload(article) -> dict:
    """ORM 整行或内存兜底 dict 统一裁剪为读者可见字段,account_name 顺带脱敏。"""
    getter = article.get if isinstance(article, dict) else getattr
    payload = {}
    for field in PUBLIC_ARTICLE_FIELDS:
        value = getter(article, field, None)
        if field == "account_name":
            value = public_account_name(value)
        payload[field] = value
    return payload
