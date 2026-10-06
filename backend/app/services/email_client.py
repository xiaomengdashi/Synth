"""163 邮箱 IMAP 拉取与解析:白名单发件人的 .md 附件 → EmailMessageData。

解析(纯函数)与网络(_connect/fetch)分离,前者可离线单测。
网易怪癖:163 的 IMAP 服务器要求客户端连接后发送 RFC 2971 ID 命令,
否则可能拒绝服务;TEXT 搜索不可用,因此只按日期 SEARCH、发件人在本地过滤。
"""

from __future__ import annotations

import datetime
import email
import email.message
import email.policy
import email.utils
import hashlib
import imaplib
import re
from dataclasses import dataclass, field

BILIBILI_URL_RE = re.compile(
    r"https?://(?:www\.)?bilibili\.com/video/[A-Za-z0-9]+|https?://b23\.tv/[A-Za-z0-9]+"
)
_REPLY_PREFIX_RE = re.compile(r"^\s*(?:re|fwd|回复|转发)\s*[:：]\s*", re.IGNORECASE)
_TITLE_LINE_RE = re.compile(r"^#\s+(\S.*)$")


@dataclass
class EmailMessageData:
    message_id: str
    from_addr: str
    subject: str
    date: str
    md_attachments: list[dict] = field(default_factory=list)


def parse_whitelist(raw: str) -> list[str]:
    """白名单配置是逗号/分号/空白分隔的地址串,统一小写。"""
    tokens = re.split(r"[,;\s]+", str(raw or ""))
    result: list[str] = []
    for token in tokens:
        value = token.strip().lower()
        if value and value not in result:
            result.append(value)
    return result


def parse_sender_address(from_header: str) -> str:
    return email.utils.parseaddr(str(from_header or ""))[1].lower()


def is_from_whitelisted(from_addr: str, whitelist: list[str]) -> bool:
    return from_addr.lower() in {item.lower() for item in whitelist}


def pick_md_attachments(msg: email.message.Message) -> list[dict]:
    parts = list(msg.iter_attachments()) if msg.is_multipart() else [msg]
    result: list[dict] = []
    for part in parts:
        filename = part.get_filename() or ""
        disposition = part.get_content_disposition()
        is_md = filename.lower().endswith(".md") or (
            part.get_content_type() == "text/markdown" and disposition == "attachment"
        )
        if not is_md:
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue  # 解不出正文的附件跳过,不阻断整封邮件
        charset = part.get_content_charset() or "utf-8"
        try:
            content = payload.decode(charset, errors="replace")
        except LookupError:
            content = payload.decode("utf-8", errors="replace")
        result.append({"filename": filename or "attachment.md", "content": content})
    return result


def title_from_markdown(content: str, subject: str, filename: str) -> str:
    for line in (content or "").splitlines()[:40]:
        match = _TITLE_LINE_RE.match(line)
        if match:
            return match.group(1).strip()[:200]
    candidate = (subject or "").strip()
    while candidate:
        stripped = _REPLY_PREFIX_RE.sub("", candidate, count=1)
        if stripped == candidate:
            break
        candidate = stripped.strip()
    if candidate:
        return candidate[:200]
    stem = (filename or "").strip()
    if stem.lower().endswith(".md"):
        stem = stem[:-3]
    return stem.strip()[:200] or "未命名笔记"


def extract_bilibili_url(content: str) -> str:
    match = BILIBILI_URL_RE.search(content or "")
    return match.group(0) if match else ""


def parse_raw_message(raw: bytes, whitelist: list[str]) -> EmailMessageData | None:
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    from_addr = parse_sender_address(str(msg.get("From") or ""))
    if not is_from_whitelisted(from_addr, whitelist):
        return None
    attachments = pick_md_attachments(msg)
    if not attachments:
        return None
    subject = str(msg.get("Subject") or "").strip()
    try:
        date_value = email.utils.parsedate_to_datetime(str(msg.get("Date")))
        date_text = date_value.strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        date_text = ""
    message_id = str(msg.get("Message-ID") or "").strip()
    if not message_id:
        digest = hashlib.sha1(f"{from_addr}|{subject}|{date_text}".encode("utf-8")).hexdigest()
        message_id = f"sha1-{digest}"
    return EmailMessageData(message_id, from_addr, subject, date_text, attachments)


FETCH_SINCE_DAYS = 30
IMAP_TIMEOUT_SECONDS = 30


class EmailAuthError(Exception):
    pass


class EmailFetchError(Exception):
    pass


def _connect(config: dict) -> imaplib.IMAP4_SSL:
    host = (str(config.get("imapHost") or "").strip() or "imap.163.com")
    user = str(config.get("imapUser") or "").strip()
    password = str(config.get("imapPassword") or "").strip()
    if not user or not password:
        raise EmailAuthError("请先在「邮箱导入」页配置邮箱账号与客户端授权码。")
    try:
        connection = imaplib.IMAP4_SSL(host, 993, timeout=IMAP_TIMEOUT_SECONDS)
        connection.login(user, password)
    except imaplib.IMAP4.error as exc:
        raise EmailAuthError(
            "邮箱登录失败：请确认已在 163 网页版「设置 → POP3/SMTP/IMAP」开启 IMAP 服务，"
            "并使用客户端授权码（不是登录密码）。"
        ) from exc
    except (OSError, TimeoutError) as exc:
        raise EmailFetchError("邮箱连接失败，请检查网络后重试。") from exc
    # 网易要求 RFC 2971 ID 命令(imaplib 未内置),缺失会被拒绝服务;失败不阻断,兼容其他邮箱
    try:
        imaplib.Commands["ID"] = ("AUTH",)
        connection._simple_command("ID", '("name" "SynthAI" "version" "1.0.0")')
    except Exception:
        pass
    return connection


def fetch_whitelisted_messages(config: dict) -> list[EmailMessageData]:
    whitelist = parse_whitelist(config.get("imapSenderWhitelist") or "")
    if not whitelist:
        raise EmailFetchError("请先配置发件人白名单，再拉取邮件。")
    connection = _connect(config)
    try:
        status, _ = connection.select("INBOX", readonly=True)
        if status != "OK":
            raise EmailFetchError("无法打开收件箱。")
        since = (datetime.date.today() - datetime.timedelta(days=FETCH_SINCE_DAYS)).strftime("%d-%b-%Y")
        status, data = connection.search(None, "SINCE", since)
        if status != "OK" or not data or not data[0]:
            return []
        messages: list[EmailMessageData] = []
        for num in data[0].split():
            status, fetched = connection.fetch(num, "(RFC822)")
            if status != "OK" or not fetched:
                continue
            for item in fetched:
                if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (bytes, bytearray)):
                    parsed = parse_raw_message(bytes(item[1]), whitelist)
                    if parsed is not None:
                        messages.append(parsed)
        return messages
    except imaplib.IMAP4.abort as exc:
        raise EmailFetchError("邮箱连接中断，请稍后重试。") from exc
    finally:
        try:
            connection.logout()
        except Exception:
            pass
