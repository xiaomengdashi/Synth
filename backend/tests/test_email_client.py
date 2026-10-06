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
