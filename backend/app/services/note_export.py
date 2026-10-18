"""笔记导出:文章 → Obsidian 兼容 Markdown 笔记。

纯读 + 文件生成,不动表结构。正文提取按入库形态分路:
微信复刻/X 长文的 HTML 不做 HTML→md,只提纯文字(BeautifulSoup 先例
wechat_summary_regen);X 推文/长文从 marker 块的 JSON 取正文;其余来源取摘要段
之后的 markdown。json 损坏回退仅摘要+原文链接,导出不报错。
"""

import datetime
import json
import re

from bs4 import BeautifulSoup

from app.services.article_public import public_account_name

# 摘要段头,与前端 Article.tsx 的 SUMMARY_SECTION_PATTERN 同形:## 内容摘要\n\n<文本>\n\n--- 之后是正文
_SUMMARY_SECTION_RE = re.compile(r"^##\s*(?:(?:AI\s*)?摘要|内容摘要)\s*\n+([\s\S]*?)\n+\s*---\s*\n*")
_HTML_BLOCK_RE = re.compile(
    r"<!-- HTML_CONTENT_START -->\n?(.*?)\n?<!-- HTML_CONTENT_END -->", re.DOTALL
)
_X_ARTICLE_BLOCK_RE = re.compile(r"<!-- X_ARTICLE_START -->\n?(.*?)\n?<!-- X_ARTICLE_END -->", re.DOTALL)
_X_CONTENT_BLOCK_RE = re.compile(r"<!-- X_CONTENT_START -->\n?(.*?)\n?<!-- X_CONTENT_END -->", re.DOTALL)
# publish_time 是自由字符串(article.py),只认前 10 位是 YYYY-MM-DD 的值,否则回退 created_at
_DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
# frontmatter 标量危险字符:冒号/引号/反斜杠/井号/换行、行首结构符、首尾空白、空值
_YAML_DANGER_RE = re.compile(r"[:\"'\r\n#\\\\]|^[ !&*?\[\]{}|>%@`-]|[\s`]$|^$")
# YAML 1.1 裸词:纯数字(含小数)与 true/false/null/yes/no/on/off/~/True/Null 等大小写变体,
# 不加引号会被 Obsidian 解析为 number/bool/null,属性类型漂移
_YAML_BARE_SCALAR_RE = re.compile(
    r"^\d+(?:\.\d+)?$|^(?:true|false|null|yes|no|on|off|~)$", re.IGNORECASE
)
# 文件名非法字符:Windows 保留 + 控制符
_UNSAFE_FILENAME_RE = re.compile(r"[/\\:*?\"<>|\x00-\x1f]")

# 平台中文名,同前端 ArticleList.tsx sourceLabel 映射
SOURCE_LABELS = {
    "wechat": "微信公众号",
    "bilibili": "Bilibili",
    "x": "X / Twitter",
}


def source_label(source_type) -> str:
    """平台中文名;未知来源归「网页」,与前端展示口径一致。"""
    return SOURCE_LABELS.get(str(source_type or ""), "网页")


def article_field(article, name: str):
    """统一字段访问:接受 ORM 实体或内存兜底的 dict(详情接口同款兜底路径)。"""
    if isinstance(article, dict):
        return article.get(name)
    return getattr(article, name, None)


def yaml_safe(value) -> str:
    """frontmatter 标量转义(Obsidian 兼容):含危险字符或 YAML 1.1 裸词时整体加双引号并转义。

    只处理标量危险字符与裸词,不做完整 YAML 序列化(不引依赖)。
    """
    text = str(value if value is not None else "")
    if _YAML_DANGER_RE.search(text) or _YAML_BARE_SCALAR_RE.match(text):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def safe_filename(name, max_length: int = 80) -> str:
    """剔除文件名非法字符与控制符、折叠空白、截 max_length 字符;清空后兜底「笔记」。"""
    cleaned = _UNSAFE_FILENAME_RE.sub("", str(name or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_length].strip() or "笔记"


def note_date(publish_time, created_at) -> str:
    """笔记日期:publish_time(自由字符串)前 10 位是日期式则用,否则回退 created_at(支持 datetime 与 ISO 串)。"""
    value = str(publish_time or "").strip()
    if _DATE_PREFIX_RE.match(value):
        return value[:10]
    if isinstance(created_at, datetime.datetime):
        return created_at.strftime("%Y-%m-%d")
    text = str(created_at or "").strip()
    if _DATE_PREFIX_RE.match(text):
        return text[:10]
    return ""


def extract_summary_section(content_md: str) -> tuple[str, str]:
    """拆开头摘要段:返回 (摘要文本, 摘要段之后的正文)。

    无摘要段头(视频笔记型:笔记即成品直接入库,task_service.build_video_markdown
    有 notes 时 return notes)时摘要为空串、整篇 content_md 作正文。
    """
    text = str(content_md or "")
    match = _SUMMARY_SECTION_RE.match(text)
    if match:
        return match.group(1).strip(), text[match.end():].strip()
    return "", text.strip()


def _json_block(match) -> dict | None:
    """marker 块内 JSON 解析;损坏(截断/非 JSON)返回 None,调用方回退不报错。"""
    try:
        parsed = json.loads(match.group(1).strip())
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def extract_note_body(content_md: str) -> str:
    """按入库形态还原导出正文:

    - HTML 复刻块(微信/html 导入):不做 HTML→md,提纯 HTML 文字(与 X 长文 body_html 同先例)
    - X 长文块:replica.text 优先,为空则 body_html 提取纯文本(先例 wechat_summary_regen)
    - X 推文块:tweet_text,空则 article_preview.preview_text(循 task_service 入库口径)
    - 其余(bilibili/网页等):摘要段之后的 markdown 正文
    """
    text = str(content_md or "")
    html_match = _HTML_BLOCK_RE.search(text)
    if html_match:
        return BeautifulSoup(html_match.group(1), "html.parser").get_text("\n", strip=True)
    article_match = _X_ARTICLE_BLOCK_RE.search(text)
    if article_match:
        replica = _json_block(article_match)
        if replica is None:
            return ""
        body = str(replica.get("text") or "").strip()
        if body:
            return body
        html = str(replica.get("body_html") or "").strip()
        if html:
            return BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
        return ""
    content_match = _X_CONTENT_BLOCK_RE.search(text)
    if content_match:
        payload = _json_block(content_match)
        if payload is None:
            return ""
        body = str(payload.get("tweet_text") or "").strip()
        if not body:
            preview = payload.get("article_preview")
            body = str((preview or {}).get("preview_text") or "").strip()
        return body
    _, body = extract_summary_section(text)
    return body


def build_note_markdown(article) -> str:
    """组 Obsidian 兼容笔记:YAML frontmatter + 摘要 + 正文 + 原文链接行。"""
    content_md = str(article_field(article, "content_md") or "")
    summary_section, _ = extract_summary_section(content_md)
    summary = (summary_section or str(article_field(article, "summary") or "")).strip()
    body = extract_note_body(content_md).strip()
    category = str(article_field(article, "category") or "").strip() or "未分类"

    lines = [
        "---",
        f"title: {yaml_safe(article_field(article, 'title'))}",
        f"source_url: {yaml_safe(article_field(article, 'original_url'))}",
        f"source: {yaml_safe(source_label(article_field(article, 'source_type')))}",
        f"category: {yaml_safe(category)}",
    ]
    # 邮件导入文章的作者位是发件人邮箱地址,导出文件随读者级接口分发,统一脱敏
    account_name = public_account_name(article_field(article, "account_name"))
    if account_name:
        lines.append(f"account_name: {yaml_safe(account_name)}")
    date = note_date(article_field(article, "publish_time"), article_field(article, "created_at"))
    if date:
        lines.append(f"date: {yaml_safe(date)}")
    lines.extend(["---", ""])

    if summary:
        lines.extend(["## 内容摘要", "", summary, ""])
    if body:
        lines.extend([body, ""])
    original_url = str(article_field(article, "original_url") or "").strip()
    if original_url:
        lines.append(f"> 原文：{original_url}")
    return "\n".join(lines).rstrip() + "\n"
