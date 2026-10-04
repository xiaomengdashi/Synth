# 163 邮箱 md 附件导入书房 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 后台手动拉取 163 邮箱白名单发件人的邮件,把每个 `.md` 附件入库为一篇 `source_type='bilibili'` 的文章(正文一字不动)。

**Architecture:** 新增 `email_client.py`(标准库 imaplib 直连 IMAP,网络与解析分离)+ `routers/email_import.py`(`/api/v1/email/test`、`/api/v1/email/fetch`,入库与去重在路由层,与 `import-html` 先例一致);配置走现有 app_settings KV;前端后台新增「邮箱导入」页。设计依据:`docs/superpowers/specs/2026-10-04-163-email-md-import-design.md`。

**Tech Stack:** FastAPI + SQLAlchemy(async) + pytest(现有 `backend/.venv`);React + Zustand + React Router;IMAP 用 Python 标准库 `imaplib`/`email`,**零新增依赖**。

## Global Constraints

- 不新增任何 Python 依赖;IMAP 只用标准库。
- `source_type` 恒为 `'bilibili'`;**前台零改动**(来源枚举/色条/筛选复用现有)。
- `content_md` 存附件原文,不改一字(含格式瑕疵)。
- 后台接口全部挂 `Depends(require_admin)`(`X-Admin-Token`);面向用户文案全中文。
- 后端测试:`cd backend && .venv/bin/python -m pytest tests/<file> -v`;前端验证:`cd frontend && npx vite build`。
- 本地后端 8000 无 `--reload`:每次改完后端手测前须重启后端进程。
- 提交信息 `feat:`/`docs:` 前缀 + 中文描述;每 Task 一提交,用显式路径 `git add`。
- 注释只写约束和坑(如网易 ID 命令),不写流水账。

---

### Task 1: 配置层——IMAP 配置项与已导入 Message-ID 存取

**Files:**
- Modify: `backend/app/services/settings_store.py`
- Modify: `backend/app/routers/config.py`
- Test: `backend/tests/test_email_settings.py`(新建)

**Interfaces:**
- Consumes: 现有 `SUPPORTED_KEYS`/`save_settings`(掩码跳过)/`public_settings`/`mask_secret`、categories 的「内部 key 直接读写 AppSetting」模式。
- Produces:
  - `SUPPORTED_KEYS` 新增 `imapHost`、`imapUser`、`imapPassword`、`imapSenderWhitelist`(顺序排最后,保持旧键位置不变);
  - `public_settings()` 返回新增:`imapHost`(明文)、`imapUser`(明文)、`imapSenderWhitelist`(明文)、`imapPassword`(掩码)、`imapConfigured`(bool:user 与 password 均非空);
  - `async load_processed_message_ids() -> list[str]`、`async record_processed_message_ids(new_ids: list[str]) -> list[str]`(合并去重、FIFO 保留最近 500 条,存内部 key `emailProcessedMessageIds`,不进 SUPPORTED_KEYS、不对前端暴露);
  - `routers/config.py` 的 `AppConfigModel` 新增同名字段 `imapHost/imapUser/imapPassword/imapSenderWhitelist`(默认 `""`)。

- [ ] **Step 1: 写失败测试** `backend/tests/test_email_settings.py`(照 `test_config_cleanup.py` 的 tmp_path 引擎 + monkeypatch 模式):

```python
import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.services import settings_store


def _make_sessions(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 's.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(prepare())
    return engine, sessions


def test_public_settings_masks_imap_password(tmp_path, monkeypatch):
    engine, sessions = _make_sessions(tmp_path)
    monkeypatch.setattr(settings_store, "AsyncSessionLocal", sessions)
    asyncio.run(settings_store.save_settings({
        "imapUser": "kolane@163.com",
        "imapPassword": "authcode-12345",
        "imapSenderWhitelist": "friend@qq.com",
    }))

    public = settings_store.public_settings(asyncio.run(settings_store.load_settings()))
    assert "authcode-12345" not in str(public)
    assert public["imapPassword"] == "••••2345"
    assert public["imapUser"] == "kolane@163.com"
    assert public["imapHost"] == ""
    assert public["imapSenderWhitelist"] == "friend@qq.com"
    assert public["imapConfigured"] is True
    asyncio.run(engine.dispose())


def test_imap_password_not_configured_when_user_missing(tmp_path, monkeypatch):
    engine, sessions = _make_sessions(tmp_path)
    monkeypatch.setattr(settings_store, "AsyncSessionLocal", sessions)
    asyncio.run(settings_store.save_settings({"imapPassword": "authcode-12345"}))
    public = settings_store.public_settings(asyncio.run(settings_store.load_settings()))
    assert public["imapConfigured"] is False
    asyncio.run(engine.dispose())


def test_processed_message_ids_roundtrip_and_cap(tmp_path, monkeypatch):
    engine, sessions = _make_sessions(tmp_path)
    monkeypatch.setattr(settings_store, "AsyncSessionLocal", sessions)

    asyncio.run(settings_store.record_processed_message_ids(["a@1", "b@2"]))
    asyncio.run(settings_store.record_processed_message_ids(["b@2", "c@3"]))
    assert asyncio.run(settings_store.load_processed_message_ids()) == ["a@1", "b@2", "c@3"]

    batch = [f"id-{n}" for n in range(600)]
    kept = asyncio.run(settings_store.record_processed_message_ids(batch))
    assert len(kept) == 500
    assert kept[0] == "id-100"
    assert kept[-1] == "id-599"
    asyncio.run(engine.dispose())
```

- [ ] **Step 2: 跑测试确认失败** — Run: `cd backend && .venv/bin/python -m pytest tests/test_email_settings.py -v`,Expected: FAIL(`imapConfigured`/`load_processed_message_ids` 不存在)。

- [ ] **Step 3: 实现** — `settings_store.py` 三处修改:

```python
# L20 SUPPORTED_KEYS 改为:
SUPPORTED_KEYS = (
    "apiKey", "baseUrl", "modelName", "tikhubApiKey", "minimaxApiKey",
    "imapHost", "imapUser", "imapPassword", "imapSenderWhitelist",
)
```

`public_settings` 的 return 字典追加(函数内先取 `imap_user = str(values.get("imapUser") or "").strip()`、`imap_password = str(values.get("imapPassword") or "").strip()`):

```python
        "imapHost": str(values.get("imapHost") or ""),
        "imapUser": imap_user,
        "imapPassword": mask_secret(imap_password),
        "imapSenderWhitelist": str(values.get("imapSenderWhitelist") or ""),
        "imapConfigured": bool(imap_user and imap_password),
```

文件末尾(categories/ADMIN_TOKEN 段之后)新增,内部 key 读写照 `save_categories` 的 upsert 模式:

```python
EMAIL_PROCESSED_KEY = "emailProcessedMessageIds"
EMAIL_PROCESSED_CAP = 500


async def load_processed_message_ids() -> list[str]:
    """已入库邮件的 Message-ID 清单(JSON 数组),用于拉取去重。"""
    import json as _json

    async with AsyncSessionLocal() as session:
        row = await session.execute(select(AppSetting).where(AppSetting.key == EMAIL_PROCESSED_KEY))
        stored = row.scalar_one_or_none()
    if not stored or not stored.value:
        return []
    try:
        ids = _json.loads(stored.value)
    except ValueError:
        return []
    return [str(item) for item in ids if str(item)]


async def record_processed_message_ids(new_ids: list[str]) -> list[str]:
    """合并新入库的 Message-ID,去重后 FIFO 保留最近 EMAIL_PROCESSED_CAP 条。"""
    import datetime as _dt
    import json as _json

    incoming = [str(item).strip() for item in new_ids if str(item).strip()]
    merged = [item for item in await load_processed_message_ids() if item not in set(incoming)]
    seen: set[str] = set()
    merged = [item for item in merged + incoming if not (item in seen or seen.add(item))]
    kept = merged[-EMAIL_PROCESSED_CAP:]

    async with AsyncSessionLocal() as session:
        row = await session.execute(select(AppSetting).where(AppSetting.key == EMAIL_PROCESSED_KEY))
        stored = row.scalar_one_or_none()
        payload = _json.dumps(kept, ensure_ascii=False)
        if stored is None:
            session.add(AppSetting(key=EMAIL_PROCESSED_KEY, value=payload))
        else:
            stored.value = payload
            stored.updated_at = _dt.datetime.now(_dt.UTC).replace(tzinfo=None)
        await session.commit()
    return kept
```

`routers/config.py` 的 `AppConfigModel` 追加:

```python
    imapHost: str = ""
    imapUser: str = ""
    imapPassword: str = ""
    imapSenderWhitelist: str = ""
```

- [ ] **Step 4: 跑测试确认通过** — Run: `cd backend && .venv/bin/python -m pytest tests/test_email_settings.py tests/test_config_cleanup.py -v`,Expected: 全 PASS(旧配置测试不回归)。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/settings_store.py backend/app/routers/config.py backend/tests/test_email_settings.py
git commit -m "feat: 邮箱导入配置层——IMAP 账号/授权码/发件人白名单与已导入 Message-ID 存取"
```

---

### Task 2: 邮件解析纯函数——发件人/主题/日期/.md 附件/标题/B站链接

**Files:**
- Create: `backend/app/services/email_client.py`
- Test: `backend/tests/test_email_client.py`(新建)

**Interfaces:**
- Consumes: 仅标准库(`email`、`re`、`hashlib`、`dataclasses`、`datetime`)。
- Produces(Task 3/4 依赖,签名固定):
  - `@dataclass EmailMessageData`:字段 `message_id: str, from_addr: str, subject: str, date: str, md_attachments: list[dict]`(dict 为 `{"filename": str, "content": str}`);
  - `parse_whitelist(raw: str) -> list[str]`(逗号/分号/空白/换行分隔,小写、去空去重);
  - `parse_sender_address(from_header: str) -> str`;
  - `is_from_whitelisted(from_addr: str, whitelist: list[str]) -> bool`;
  - `pick_md_attachments(msg) -> list[dict]`(只取 `.md` 文件名或 `text/markdown` 且 disposition 为 attachment 的部分,charset 缺省 utf-8);
  - `title_from_markdown(content: str, subject: str, filename: str) -> str`(md 首个 `# ` 一级标题 → 主题去 Re:/Fwd: → 文件名去扩展名 → `未命名笔记`);
  - `extract_bilibili_url(content: str) -> str`;
  - `parse_raw_message(raw: bytes, whitelist: list[str]) -> EmailMessageData | None`(白名单外返回 None;无 Message-ID 时用 sha1 兜底;date 格式 `%Y-%m-%d %H:%M`)。

- [ ] **Step 1: 写失败测试** `backend/tests/test_email_client.py`:

```python
import email.message
import email.policy

from app.services.email_client import (
    EmailMessageData,
    extract_bilibili_url,
    is_from_whitelisted,
    parse_raw_message,
    parse_sender_address,
    parse_whitelist,
    pick_md_attachments,
    title_from_markdown,
)


def _build_message(from_addr: str, subject: str, md_body: str | None, md_name: str = "notes.md") -> bytes:
    msg = email.message.EmailMessage(policy=email.policy.default)
    msg["From"] = from_addr
    msg["To"] = "kolane@163.com"
    msg["Subject"] = subject
    msg["Message-ID"] = "<test-0001@163.com>"
    msg["Date"] = "Sat, 04 Oct 2026 10:30:00 +0800"
    msg.set_content("邮件正文,不是笔记。")
    if md_body is not None:
        msg.add_attachment(md_body.encode("utf-8"), maintype="text", subtype="markdown", filename=md_name)
    return msg.as_bytes()


def test_parse_whitelist_normalizes():
    assert parse_whitelist("A@163.com, b@qq.com;;\n c@163.com A@163.com") == ["a@163.com", "b@qq.com", "c@163.com"]
    assert parse_whitelist("") == []


def test_parse_sender_address_handles_display_name():
    assert parse_sender_address('"张三" <zhang@163.com>') == "zhang@163.com"
    assert parse_sender_address("zhang@163.com") == "zhang@163.com"


def test_whitelist_match_is_case_insensitive():
    assert is_from_whitelisted("Zhang@163.com", ["zhang@163.com"]) is True
    assert is_from_whitelisted("other@163.com", ["zhang@163.com"]) is False


def test_pick_md_attachments_only_md():
    msg = email.message_from_bytes(
        _build_message("a@163.com", "t", "# 标题\n\n正文", md_name="笔记.md"), policy=email.policy.default
    )
    attachments = pick_md_attachments(msg)
    assert len(attachments) == 1
    assert attachments[0]["filename"] == "笔记.md"
    assert attachments[0]["content"] == "# 标题\n\n正文"


def test_pick_md_attachments_skips_other_files():
    msg = email.message.EmailMessage(policy=email.policy.default)
    msg["From"] = "a@163.com"; msg["Subject"] = "t"; msg["Date"] = "Sat, 04 Oct 2026 10:30:00 +0800"
    msg.set_content("正文")
    msg.add_attachment(b"pdf-bytes", maintype="application", subtype="pdf", filename="doc.pdf")
    assert pick_md_attachments(msg) == []


def test_parse_raw_message_whitelisted():
    parsed = parse_raw_message(_build_message("Zhang@163.com", "B站笔记", "# 标题"), ["zhang@163.com"])
    assert parsed is not None
    assert parsed.message_id == "<test-0001@163.com>"
    assert parsed.from_addr == "zhang@163.com"
    assert parsed.subject == "B站笔记"
    assert parsed.date == "2026-10-04 10:30"
    assert parsed.md_attachments and parsed.md_attachments[0]["content"] == "# 标题"


def test_parse_raw_message_outside_whitelist_returns_none():
    assert parse_raw_message(_build_message("x@163.com", "t", "# t"), ["zhang@163.com"]) is None


def test_parse_raw_message_without_md_attachment_returns_none():
    parsed = parse_raw_message(_build_message("zhang@163.com", "t", None), ["zhang@163.com"])
    assert parsed is None


def test_parse_raw_message_message_id_fallback():
    raw = _build_message("zhang@163.com", "t", "# t")
    raw = raw.replace(b"<test-0001@163.com>", b"")
    parsed = parse_raw_message(raw, ["zhang@163.com"])
    assert parsed is not None and parsed.message_id.startswith("sha1-")


def test_title_from_markdown_prefers_h1():
    assert title_from_markdown("前言\n\n# 网络通信原理\n\n## 一、x", "邮件主题", "n.md") == "网络通信原理"


def test_title_from_markdown_fallback_subject_then_filename():
    assert title_from_markdown("没有标题", "Re: B站总结", "n.md") == "B站总结"
    assert title_from_markdown("没有标题", "", "B站笔记.md") == "B站笔记"
    assert title_from_markdown("", "", "") == "未命名笔记"


def test_extract_bilibili_url():
    assert extract_bilibili_url("看 https://www.bilibili.com/video/BV17x6hYZEzJ 学习") == "https://www.bilibili.com/video/BV17x6hYZEzJ"
    assert extract_bilibili_url("短链 https://b23.tv/abc123") == "https://b23.tv/abc123"
    assert extract_bilibili_url("没有链接") == ""


def test_email_message_data_shape():
    data = EmailMessageData("m", "a", "s", "d", [])
    assert data.md_attachments == []
```

- [ ] **Step 2: 跑测试确认失败** — Run: `cd backend && .venv/bin/python -m pytest tests/test_email_client.py -v`,Expected: FAIL(ModuleNotFoundError)。

- [ ] **Step 3: 实现** — 新建 `backend/app/services/email_client.py`(本 Task 只写解析段,网络段留 Task 3 追加):

```python
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
        try:
            content = part.get_content()
        except Exception:
            continue  # 解不出正文的附件跳过,不阻断整封邮件
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        result.append({"filename": filename or "attachment.md", "content": str(content)})
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
```

- [ ] **Step 4: 跑测试确认通过** — Run: `cd backend && .venv/bin/python -m pytest tests/test_email_client.py -v`,Expected: 全 PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/email_client.py backend/tests/test_email_client.py
git commit -m "feat: 邮件解析——白名单/附件/标题/B站链接识别(纯函数,离线可测)"
```

---

### Task 3: IMAP 拉取——163 登录、ID 命令兼容、近 30 天过滤

**Files:**
- Modify: `backend/app/services/email_client.py`(追加网络段)
- Test: `backend/tests/test_email_client.py`(追加)

**Interfaces:**
- Consumes: Task 2 的 `parse_raw_message`/`parse_whitelist`。
- Produces(Task 4 依赖):
  - `class EmailAuthError(Exception)`、`class EmailFetchError(Exception)`(消息为中文,可直接透给 HTTP 400);
  - `fetch_whitelisted_messages(config: dict) -> list[EmailMessageData]`(config 取 `imapHost/imapUser/imapPassword/imapSenderWhitelist`;连接超时 30s;INBOX readonly;SINCE 30 天;**不改任何邮件标志**——去重靠 Message-ID,邮箱状态零写入)。

- [ ] **Step 1: 追加失败测试**(网络不 mock imaplib,只测可离线验证的入口行为与异常类型):

```python
import pytest

from app.services.email_client import EmailFetchError, fetch_whitelisted_messages


def test_fetch_without_whitelist_fails_fast():
    with pytest.raises(EmailFetchError) as exc_info:
        fetch_whitelisted_messages({"imapUser": "a@163.com", "imapPassword": "x", "imapSenderWhitelist": ""})
    assert "白名单" in str(exc_info.value)
```

- [ ] **Step 2: 跑测试确认失败** — Run: `cd backend && .venv/bin/python -m pytest tests/test_email_client.py -v`,Expected: FAIL(`EmailFetchError` 未定义)。

- [ ] **Step 3: 追加实现** 到 `email_client.py`:

```python
import imaplib

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
```

- [ ] **Step 4: 跑测试确认通过** — Run: `cd backend && .venv/bin/python -m pytest tests/test_email_client.py -v`,Expected: 全 PASS(含 Task 2 的用例)。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/email_client.py backend/tests/test_email_client.py
git commit -m "feat: IMAP 拉取——163 登录(RFC 2971 ID 命令兼容)、近 30 天白名单邮件只读拉取"
```

---

### Task 4: 导入接口与入库——/api/v1/email/test、/api/v1/email/fetch

**Files:**
- Create: `backend/app/routers/email_import.py`
- Modify: `backend/main.py`(import 与 include_router 两行)
- Test: `backend/tests/test_email_import.py`(新建)

**Interfaces:**
- Consumes: Task 1 `load_processed_message_ids`/`record_processed_message_ids`;Task 2/3 `EmailMessageData`/`fetch_whitelisted_messages`/`title_from_markdown`/`extract_bilibili_url`/异常类;现有 `require_admin`、`AsyncSessionLocal`、`Article`、`ARTICLES_DB`。
- Produces:
  - `POST /api/v1/email/test` → `{"ok": True, "recent_count": int}`(HTTP 400 带中文 detail 表示配置/网络错误);
  - `POST /api/v1/email/fetch` → `{"fetched": int, "imported": [{"id", "title", "filename"}], "skipped": [{"subject", "reason"}]}`;
  - 入库规则:`source_type='bilibili'`、`summary=""`、`cover_image_url=""`、`account_name=发件人`、`publish_time=邮件日期`、`original_url=正文首个 B 站链接或 ""`;成功写入 `ARTICLES_DB` 内存镜像 + Article 行;**全部附件在同一事务提交**,Message-ID 仅在文章落库成功后记录(失败自动留待重拉)。

- [ ] **Step 1: 写失败测试** `backend/tests/test_email_import.py`:

```python
import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.routers.email_import as email_import
from app.database import Base
from app.models import Article
from app.services import settings_store
from app.services.email_client import EmailMessageData
from app.services.runtime_store import ARTICLES_DB


def _setup(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 's.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(prepare())
    monkeypatch.setattr(settings_store, "AsyncSessionLocal", sessions)
    monkeypatch.setattr(email_import, "AsyncSessionLocal", sessions)
    ARTICLES_DB.clear()
    return engine, sessions


def _client():
    app = FastAPI()
    app.include_router(email_import.router)
    return TestClient(app)


def _message(message_id: str, md: str | None) -> EmailMessageData:
    attachments = [{"filename": "notes.md", "content": md}] if md is not None else []
    return EmailMessageData(
        message_id=message_id, from_addr="zhang@163.com",
        subject="B站笔记", date="2026-10-04 10:30", md_attachments=attachments,
    )


def test_fetch_imports_md_and_dedupes(tmp_path, monkeypatch):
    engine, _sessions = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        email_import, "fetch_whitelisted_messages",
        lambda config: [_message("msg-1", "# 网络原理\n\nhttps://b23.tv/abc"), _message("msg-2", None)],
    )
    client = _client()

    first = client.post("/api/v1/email/fetch").json()
    assert first["fetched"] == 2
    assert len(first["imported"]) == 1
    assert first["imported"][0]["title"] == "网络原理"
    assert first["skipped"] == [{"subject": "B站笔记", "reason": "邮件没有 .md 附件"}]

    second = client.post("/api/v1/email/fetch").json()
    assert second["imported"] == []
    assert second["skipped"] == [{"subject": "B站笔记", "reason": "已导入过，跳过"}]
    asyncio.run(engine.dispose())


def test_imported_article_fields(tmp_path, monkeypatch):
    engine, sessions = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        email_import, "fetch_whitelisted_messages", lambda config: [_message("msg-1", "# 标题\n\n正文")]
    )
    client = _client()
    data = client.post("/api/v1/email/fetch").json()
    article_id = data["imported"][0]["id"]

    async def load():
        async with sessions() as session:
            return await session.get(Article, article_id)

    article = asyncio.run(load())
    assert article is not None
    assert article.source_type == "bilibili"
    assert article.original_url == ""  # 测试正文里没有 B 站链接
    assert article.content_md == "# 标题\n\n正文"
    assert article.account_name == "zhang@163.com"
    assert article.publish_time == "2026-10-04 10:30"
    assert article.id in ARTICLES_DB
    asyncio.run(engine.dispose())


def test_fetch_without_whitelist_returns_chinese_400(tmp_path, monkeypatch):
    engine, _sessions = _setup(tmp_path, monkeypatch)
    from app.services.email_client import EmailFetchError

    def raise_no_whitelist(config):
        raise EmailFetchError("请先配置发件人白名单，再拉取邮件。")

    monkeypatch.setattr(email_import, "fetch_whitelisted_messages", raise_no_whitelist)
    response = _client().post("/api/v1/email/fetch")
    assert response.status_code == 400
    assert "白名单" in response.json()["detail"]
    asyncio.run(engine.dispose())


def test_test_endpoint_reports_recent_count(tmp_path, monkeypatch):
    engine, _sessions = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(email_import, "fetch_whitelisted_messages", lambda config: [_message("m1", "# t")])
    data = _client().post("/api/v1/email/test").json()
    assert data == {"ok": True, "recent_count": 1}
    asyncio.run(engine.dispose())
```

- [ ] **Step 2: 跑测试确认失败** — Run: `cd backend && .venv/bin/python -m pytest tests/test_email_import.py -v`,Expected: FAIL(模块不存在)。

- [ ] **Step 3: 实现** — 新建 `backend/app/routers/email_import.py`:

```python
"""后台邮箱导入：163 IMAP 拉取白名单发件人的 .md 附件,入库为 B 站来源文章。

入库/去重在路由层完成,与 import-html 先例一致;
去重靠 Message-ID(app_settings 内部 key),邮箱侧零状态写入。
"""

import asyncio
import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.database import AsyncSessionLocal
from app.models import Article
from app.routers.admin_auth import require_admin
from app.services import settings_store
from app.services.email_client import (
    EmailAuthError,
    EmailFetchError,
    extract_bilibili_url,
    fetch_whitelisted_messages,
    title_from_markdown,
)
from app.services.runtime_store import ARTICLES_DB

router = APIRouter()


def _http_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


async def _import_articles_for_message(message: EmailMessageData) -> list[dict]:
    """一个 md 附件一篇 Article;同一事务提交,失败则整封重试。"""
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    imported: list[dict] = []
    async with AsyncSessionLocal() as session:
        for attachment in message.md_attachments:
            title = title_from_markdown(attachment["content"], message.subject, attachment["filename"])
            article_id = str(uuid.uuid4())
            article_data = {
                "id": article_id,
                "title": title,
                "summary": "",
                "content_md": attachment["content"],
                "original_url": extract_bilibili_url(attachment["content"]),
                "source_type": "bilibili",
                "cover_image_url": "",
                "account_name": message.from_addr,
                "publish_time": message.date,
                "created_at": now.isoformat(),
            }
            ARTICLES_DB[article_id] = article_data
            session.add(Article(
                id=article_id,
                title=title,
                summary="",
                content_md=attachment["content"],
                original_url=article_data["original_url"],
                source_type="bilibili",
                cover_image_url="",
                account_name=message.from_addr,
                publish_time=message.date,
                created_at=now,
            ))
            imported.append({"id": article_id, "title": title, "filename": attachment["filename"]})
        await session.commit()
    return imported


@router.post("/test")
async def test_email_connection(_: None = Depends(require_admin)):
    config = await settings_store.load_settings()
    try:
        messages = await asyncio.to_thread(fetch_whitelisted_messages, config)
    except (EmailAuthError, EmailFetchError) as exc:
        raise _http_error(exc) from exc
    return {"ok": True, "recent_count": len(messages)}


@router.post("/fetch")
async def fetch_email_articles(_: None = Depends(require_admin)):
    config = await settings_store.load_settings()
    try:
        messages = await asyncio.to_thread(fetch_whitelisted_messages, config)
    except (EmailAuthError, EmailFetchError) as exc:
        raise _http_error(exc) from exc

    processed = set(await settings_store.load_processed_message_ids())
    imported: list[dict] = []
    skipped: list[dict] = []
    newly_done: list[str] = []
    for message in messages:
        if not message.md_attachments:
            skipped.append({"subject": message.subject, "reason": "邮件没有 .md 附件"})
            continue
        if message.message_id in processed:
            skipped.append({"subject": message.subject, "reason": "已导入过，跳过"})
            continue
        try:
            imported.extend(await _import_articles_for_message(message))
        except Exception:
            skipped.append({"subject": message.subject, "reason": "入库失败，下次拉取会重试"})
            continue
        newly_done.append(message.message_id)
    if newly_done:
        await settings_store.record_processed_message_ids(newly_done)
    return {"fetched": len(messages), "imported": imported, "skipped": skipped}
```

`backend/main.py` 修改两处:

```python
# L12 import 行改为:
from app.routers import articles, tasks, config, tikhub, models, categories, admin_auth, email_import

# 路由段追加:
app.include_router(email_import.router, prefix="/api/v1/email", tags=["email"])
```

- [ ] **Step 4: 跑测试确认通过** — Run: `cd backend && .venv/bin/python -m pytest tests/test_email_import.py -v`,Expected: 全 PASS。
- [ ] **Step 5: 全量后端回归** — Run: `cd backend && .venv/bin/python -m pytest tests -q`,Expected: 全 PASS(不破坏既有测试)。

- [ ] **Step 6: 提交**

```bash
git add backend/app/routers/email_import.py backend/main.py backend/tests/test_email_import.py
git commit -m "feat: 邮箱导入接口——测试连接/拉取入库(B站来源)与 Message-ID 去重"
```

---

### Task 5: 前端——「邮箱导入」页、配置链路、导航与路由

**Files:**
- Create: `frontend/src/features/email/pages/AdminEmailImport.tsx`
- Modify: `frontend/src/features/config/types.ts`
- Modify: `frontend/src/features/app/store/useAppStore.ts`(仅 setConfig 的 body)
- Modify: `frontend/src/App.tsx`(lazy import + Route)
- Modify: `frontend/src/components/AdminLayout.tsx`(NAV_GROUPS + 面包屑 + Mail 图标)

**Interfaces:**
- Consumes: 后端 `/api/v1/config`(Task 1 已含 imap 字段)、`/api/v1/email/test`、`/api/v1/email/fetch`(两接口挂 `require_admin`,必须走 `adminFetch`——它自动附带 `X-Admin-Token`,来自 `frontend/src/utils/adminAuth`;`requestJson` 是裸 fetch 不带令牌,仅适用于无鉴权接口)。
- Produces: 路由 `/admin/email`;导航组「系统 → 邮箱导入」。

- [ ] **Step 1: 扩展类型** `frontend/src/features/config/types.ts` 的 `AppConfig` 追加:

```ts
  imapHost?: string;
  imapUser?: string;
  imapPassword?: string;
  imapSenderWhitelist?: string;
  imapConfigured?: boolean;
```

- [ ] **Step 2: 扩展 setConfig 请求体** `frontend/src/features/app/store/useAppStore.ts` 中 `body: JSON.stringify({...})` 改为:

```ts
        body: JSON.stringify({
          apiKey: config.apiKey, baseUrl: config.baseUrl, modelName: config.modelName,
          minimaxApiKey: config.minimaxApiKey ?? '',
          imapHost: config.imapHost ?? '', imapUser: config.imapUser ?? '',
          imapPassword: config.imapPassword ?? '', imapSenderWhitelist: config.imapSenderWhitelist ?? '',
        }),
```

- [ ] **Step 3: 新建后台页** `frontend/src/features/email/pages/AdminEmailImport.tsx`(照 AdminModelSettings 的 fetchConfig/localConfig/setConfig 模式;请求统一走 `adminFetch`,与全后台一致):

```tsx
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Mail, PlugZap, Download } from 'lucide-react';
import { adminFetch } from '../../../../utils/adminAuth';
import { useAppStore } from '../../app/store/useAppStore';
import AdminPageHeader from '../../tasks/components/AdminPageHeader';

type FetchResult = {
  fetched: number;
  imported: { id: string; title: string; filename: string }[];
  skipped: { subject: string; reason: string }[];
};

type Message = { tone: 'success' | 'error'; text: string } | null;

async function postJson<T>(url: string): Promise<T> {
  const response = await adminFetch(url, { method: 'POST' });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = (data as { detail?: string } | null)?.detail;
    throw new Error(typeof detail === 'string' ? detail : `请求失败（HTTP ${response.status}）`);
  }
  return data as T;
}

function EmailPanel() {
  const { config, setConfig, fetchConfig } = useAppStore();
  const [localConfig, setLocalConfig] = useState(config);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [message, setMessage] = useState<Message>(null);
  const [result, setResult] = useState<FetchResult | null>(null);

  useEffect(() => { void fetchConfig(); }, [fetchConfig]);
  useEffect(() => { setLocalConfig(config); }, [config]);

  const save = async (): Promise<boolean> => {
    setSaving(true);
    const ok = await setConfig(localConfig);
    setSaving(false);
    if (!ok) setMessage({ tone: 'error', text: '保存失败，请确认后端服务正在运行，然后重试。' });
    return ok;
  };

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    setMessage(null);
    if (await save()) setMessage({ tone: 'success', text: '邮箱配置已保存。' });
  };

  const handleTest = async () => {
    setTesting(true); setMessage(null);
    if (!(await save())) { setTesting(false); return; }
    try {
      const data = await postJson<{ ok: boolean; recent_count: number }>('/api/v1/email/test');
      setMessage({ tone: 'success', text: `连接成功，白名单发件人近 30 天有 ${data.recent_count} 封邮件。` });
    } catch (e) {
      setMessage({ tone: 'error', text: e instanceof Error ? e.message : '连接测试失败。' });
    } finally { setTesting(false); }
  };

  const handleFetch = async () => {
    setFetching(true); setMessage(null); setResult(null);
    if (!(await save())) { setFetching(false); return; }
    try {
      const data = await postJson<FetchResult>('/api/v1/email/fetch');
      setResult(data);
    } catch (e) {
      setMessage({ tone: 'error', text: e instanceof Error ? e.message : '拉取失败。' });
    } finally { setFetching(false); }
  };

  return (
    <div className="ac-stack">
      <section className="ac-set-card">
        <div className="ac-set-side">
          <h2><Mail size={15} /> 邮箱配置
            <span className={config.imapConfigured ? 'ac-badge success' : 'ac-badge pending'}>
              {config.imapConfigured ? '已配置' : '尚未配置'}
            </span>
          </h2>
          <p>在 163 网页版「设置 → POP3/SMTP/IMAP」开启 IMAP 服务并生成客户端授权码；授权码不是邮箱登录密码。</p>
        </div>
        <div className="ac-set-main">
          <form onSubmit={handleSave}>
            <div className="ac-field">
              <label htmlFor="imap-host">IMAP 服务器</label>
              <input id="imap-host" className="ac-input" value={localConfig.imapHost ?? ''} onChange={(event) => setLocalConfig({ ...localConfig, imapHost: event.target.value })} placeholder="imap.163.com" />
            </div>
            <div className="ac-field">
              <label htmlFor="imap-user">邮箱账号</label>
              <input id="imap-user" className="ac-input" type="email" value={localConfig.imapUser ?? ''} onChange={(event) => setLocalConfig({ ...localConfig, imapUser: event.target.value })} placeholder="you@163.com" />
            </div>
            <div className="ac-field">
              <label htmlFor="imap-password">客户端授权码</label>
              <input id="imap-password" className="ac-input" type="password" autoComplete="new-password" value={localConfig.imapPassword ?? ''} onChange={(event) => setLocalConfig({ ...localConfig, imapPassword: event.target.value })} placeholder={config.imapConfigured ? '已配置，输入新授权码可更换' : '客户端授权码'} />
              <p className="ac-help">仅保存在后端数据库，页面只显示掩码。</p>
            </div>
            <div className="ac-field">
              <label htmlFor="imap-whitelist">发件人白名单</label>
              <input id="imap-whitelist" className="ac-input" value={localConfig.imapSenderWhitelist ?? ''} onChange={(event) => setLocalConfig({ ...localConfig, imapSenderWhitelist: event.target.value })} placeholder="friend@qq.com, other@163.com" />
              <p className="ac-help">只拉取这些发件人的邮件，多个地址用逗号分隔。</p>
            </div>
            {message && <p className={`tikhub-message ${message.tone}`} role="status">{message.text}</p>}
            <div className="ac-actions">
              <button type="button" className="ac-btn secondary" onClick={() => void handleTest()} disabled={testing || fetching}>
                <PlugZap size={14} />{testing ? '测试中…' : '测试连接'}
              </button>
              <button type="button" className="ac-btn primary" onClick={() => void handleFetch()} disabled={fetching || testing}>
                <Download size={14} />{fetching ? '拉取中…' : '拉取邮件'}
              </button>
              <button type="submit" className="ac-btn secondary" disabled={saving || testing || fetching}>{saving ? '保存中…' : '保存配置'}</button>
            </div>
          </form>
        </div>
      </section>

      {result && (
        <section className="ac-set-card">
          <div className="ac-set-side">
            <h2><Download size={15} /> 本次拉取结果</h2>
            <p>白名单内符合条件的邮件 {result.fetched} 封，入库 {result.imported.length} 篇。</p>
          </div>
          <div className="ac-set-main">
            {result.imported.length > 0 && (
              <ul className="ac-help">
                {result.imported.map((item) => (
                  <li key={item.id}><Link to={`/article/${item.id}`}>{item.title}</Link>（{item.filename}）</li>
                ))}
              </ul>
            )}
            {result.imported.length === 0 && <p className="ac-help">本次没有新文章入库。</p>}
            {result.skipped.length > 0 && (
              <ul className="ac-help">
                {result.skipped.map((item, index) => (
                  <li key={`${item.subject}-${index}`}>{item.subject || '（无主题）'}：{item.reason}</li>
                ))}
              </ul>
            )}
          </div>
        </section>
      )}
    </div>
  );
}

/** 邮箱导入：163 IMAP 配置、测试连接与手动拉取 */
export default function AdminEmailImport() {
  return (
    <div>
      <AdminPageHeader summary={<span>邮箱导入：拉取白名单发件人的 md 附件笔记</span>} />
      <div className="ac-settings-page"><div className="ac-settings-content">
        <EmailPanel />
      </div></div>
    </div>
  );
}
```

注意:`adminFetch` 从 `frontend/src/utils/adminAuth` 导入(相对本页路径 `../../../../utils/adminAuth`),自动附带 `X-Admin-Token` 请求头;email 接口与 config 写接口一样挂了后台鉴权,**不要用 `requestJson`**。

- [ ] **Step 4: 注册路由与导航**

`frontend/src/App.tsx`:

```tsx
const AdminEmailImport = lazyPage(() => import('./features/email/pages/AdminEmailImport'));
// admin 子路由内追加:
<Route path="email" element={<Suspense fallback={<PageLoading />}><AdminEmailImport /></Suspense>} />
```

`frontend/src/components/AdminLayout.tsx`:

```tsx
// lucide-react import 追加 Mail
// NAV_GROUPS「系统」items 中「模型服务」之后插入:
      { path: '/admin/email', label: '邮箱导入', icon: Mail },
// useAdminBreadcrumbs 追加:
  if (pathname === '/admin/email') {
    return [{ label: '后台管理', to: '/admin' }, { label: '邮箱导入' }];
  }
```

- [ ] **Step 5: 构建验证** — Run: `cd frontend && npx vite build`,Expected: 成功,产物含 `AdminEmailImport-*.js`。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/features/email/pages/AdminEmailImport.tsx frontend/src/features/config/types.ts frontend/src/features/app/store/useAppStore.ts frontend/src/App.tsx frontend/src/components/AdminLayout.tsx
git commit -m "feat: 后台「邮箱导入」页——IMAP 配置、测试连接、手动拉取与结果反馈"
```

---

### Task 6: 全量回归与真实邮箱手动验证

**Files:** 无新改动(验证任务)。

- [ ] **Step 1: 后端全量测试** — Run: `cd backend && .venv/bin/python -m pytest tests -q`,Expected: 全 PASS。
- [ ] **Step 2: 前端构建** — Run: `cd frontend && npx vite build`,Expected: 成功。
- [ ] **Step 3: 重启本地后端**(8000 无 `--reload`)并确认 `GET /health` 正常。
- [ ] **Step 4: 用户配合的真实账号验证**(来自 spec 测试清单):163 网页版开 IMAP + 生成授权码 → 后台「邮箱导入」填配置 → 「测试连接」显示近 30 天邮件数 → 首次「拉取」入库(标题/正文/色条正确)→ 二次「拉取」0 新(去重)→ 手机上已读的邮件仍被拉取 → 非白发件人跳过 → 无一级标题回退邮件主题 → 无 B 站链接时详情页无死链 → 错误授权码提示中文。
- [ ] **Step 5: 全部通过后在部署时同步线上**(deploy 脚本 + 手动 restart;线上验证同清单)。
