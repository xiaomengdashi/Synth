import re

import httpx
import trafilatura
from bs4 import BeautifulSoup, Tag

from app.services.fetchers.tikhub import TikHubNotConfiguredError, fetch_wechat_article


# 微信 <pre><code> 内联样式会压成一行（white-space:nowrap + display:-webkit-box），优先级高于站点 CSS
_WS_NOWRAP_RE = re.compile(r"white-space\s*:\s*nowrap\s*;?", re.I)
_DISPLAY_WEBKIT_BOX_RE = re.compile(r"display\s*:\s*-webkit-box\s*;?", re.I)
_LINE_CLAMP_RE = re.compile(r"-webkit-line-clamp\s*:\s*[^;]+;?", re.I)
_BOX_ORIENT_RE = re.compile(r"-webkit-box-orient\s*:\s*[^;]+;?", re.I)
_STYLE_SEMICOLON_COLLAPSE_RE = re.compile(r";\s*;+")


def _normalize_title(title: str | None) -> str:
    if title is None:
        return "未知文章标题"
    text = str(title).strip()
    return text or "未知文章标题"


def _extract_meta_content(soup: BeautifulSoup, property_name: str) -> str:
    tag = soup.find("meta", attrs={"property": property_name})
    return str(tag.get("content") or "").strip() if tag else ""


def _clean_wechat_code_style_attr(style: str | None) -> str | None:
    if not style:
        return None
    s = _WS_NOWRAP_RE.sub("", style)
    s = _DISPLAY_WEBKIT_BOX_RE.sub("", s)
    s = _LINE_CLAMP_RE.sub("", s)
    s = _BOX_ORIENT_RE.sub("", s)
    s = _STYLE_SEMICOLON_COLLAPSE_RE.sub(";", s)
    s = s.strip().rstrip(";").strip()
    return s or None


def _normalize_wechat_code_styles(root: Tag) -> None:
    for code in root.find_all("code"):
        if not isinstance(code, Tag):
            continue
        if code.find_parent("pre") is None:
            continue
        cleaned = _clean_wechat_code_style_attr(code.get("style"))
        if cleaned:
            code["style"] = cleaned
        elif code.has_attr("style"):
            del code["style"]
        code["data-wechat-code"] = "true"
        for br in code.find_all("br"):
            br.replace_with("\n")
        for hidden in code.find_all("span", attrs={"hidden": True}):
            hidden.decompose()
        if code.get("class"):
            code["class"] = [
                cls
                for cls in code.get("class", [])
                if not str(cls).startswith("hljs") and not str(cls).startswith("language-")
            ]
            if not code["class"]:
                del code["class"]
    for pre in root.find_all("pre"):
        if not isinstance(pre, Tag):
            continue
        cleaned = _clean_wechat_code_style_attr(pre.get("style"))
        if cleaned:
            pre["style"] = cleaned
        elif pre.has_attr("style"):
            del pre["style"]


async def fetch_article_content(url: str, update_step, config=None):
    if "mp.weixin.qq.com" in url:
        return await _fetch_wechat_via_tikhub(url, update_step, config)

    update_step("正在抓取文章内容...")
    html = await fetch_article_html(url, update_step)
    result = parse_article_html(url, html)

    update_step(f"抓取成功: {result['title']}。正在解析正文并保存内容...")
    return result


async def _fetch_wechat_via_tikhub(url: str, update_step, config=None):
    """微信公众号文章统一走 TikHub H5 接口（绕过安全验证）。

    正文按原文存储（内联样式、<br> 换行、hidden 装饰等一律保留），
    由前端微信复刻视图按官方页面 CSS 渲染；代码块规范化仅用于
    trafilatura 文本提取的副本，不落库。
    """
    import asyncio

    update_step("正在通过 TikHub 接口获取公众号文章...")
    try:
        article = await asyncio.to_thread(fetch_wechat_article, url, config)
    except TikHubNotConfiguredError as exc:
        raise RuntimeError(
            "未配置 TikHub API Token，无法抓取公众号文章。请在管理后台 TikHub 抓取页填写 Token。"
        ) from exc

    update_step(f"抓取成功: {article['title']}。正在解析正文并保存内容...")

    html_content = _ensure_wechat_root(article["html_content"])

    # 摘要提取用规范化副本（代码块压行处理只为提取纯文本，不影响存储内容）
    if article.get("content_type") == "image":
        # 图片消息：正文是我们构造的摘要段落 + 长图，直接用接口给的纯文本，
        # 避免 trafilatura 把图片 URL 混入摘要
        extracted_md = article["content_text"]
    else:
        extract_root = BeautifulSoup(html_content, "html.parser")
        _normalize_wechat_code_styles(extract_root)
        extracted_md = trafilatura.extract(str(extract_root), output_format="markdown") or article["content_text"]
    return {
        "title": article["title"],
        "extracted_md": extracted_md,
        "html_content": html_content,
        "cover_image_url": article["cover_image_url"],
        "account_name": article.get("account_name") or "",
        "publish_time": article.get("publish_time") or "",
    }


def _ensure_wechat_root(html_content: str) -> str:
    """确保正文只有一个 js_content 根节点（TikHub 通常自带，缺失时补壳）。"""
    soup = BeautifulSoup(html_content or "", "html.parser")
    root = soup.find("div", id="js_content")
    if isinstance(root, Tag):
        return str(root)
    return (
        '<div class="rich_media_content js_underline_content defaultNoSetting" id="js_content">'
        f"{html_content}</div>"
    )


def _extract_wechat_page_meta(soup: BeautifulSoup) -> tuple[str, str]:
    """从手动保存的整页 HTML 中提取公众号名与发布时间。"""
    account_name = ""
    js_name = soup.find(id="js_name")
    if isinstance(js_name, Tag):
        account_name = js_name.get_text(" ", strip=True)
    if not account_name:
        nickname = re.search(r'var\s+nickname\s*=\s*(?:htmlDecode\()?"([^"]+)"', str(soup))
        if nickname:
            account_name = nickname.group(1)

    publish_time = ""
    publish_tag = soup.find(id="publish_time")
    if isinstance(publish_tag, Tag):
        publish_time = publish_tag.get_text(" ", strip=True)
    if not publish_time:
        ct_match = re.search(r'var\s+ct\s*=\s*"?(\d{10,13})"?', str(soup))
        if ct_match:
            publish_time = ct_match.group(1)
    return account_name, publish_time


def parse_article_html(url: str, html: str) -> dict:
    """Parse a saved page without making another network request."""
    soup = BeautifulSoup(html or "", "html.parser")
    title = _normalize_title(soup.title.get_text(" ", strip=True) if soup.title else None)
    cover_image_url = _extract_meta_content(soup, "og:image")

    if "mp.weixin.qq.com" in url:
        title = _normalize_title(_extract_meta_content(soup, "og:title"))
        if title == "未知文章标题":
            activity_name = soup.find(id="activity-name")
            if activity_name:
                title = _normalize_title(activity_name.get_text(" ", strip=True))
    elif "csdn.net" in url:
        title_tag = soup.find("h1", class_="title-article")
        if title_tag:
            title = _normalize_title(title_tag.get_text(" ", strip=True))
    elif "cnblogs.com" in url:
        title_tag = soup.find("span", role="heading") or soup.find("a", id="cb_post_title_url")
        if title_tag:
            title = _normalize_title(title_tag.get_text(" ", strip=True))

    main_content = _find_main_content(url, soup)
    if main_content is None:
        if "mp.weixin.qq.com" in url:
            raise ValueError("保存的微信 HTML 中没有找到 #js_content，可能仍是验证页。")
        extracted_md = trafilatura.extract(html, output_format="markdown") or "> 无法提取文章正文。"
        return {
            "title": title,
            "extracted_md": extracted_md,
            "html_content": "",
            "cover_image_url": cover_image_url,
        }

    account_name = ""
    publish_time = ""
    if "mp.weixin.qq.com" in url:
        # 微信正文按原文存储，代码规范化只作用于提取副本
        account_name, publish_time = _extract_wechat_page_meta(soup)
        html_content = str(main_content)
        extract_root = BeautifulSoup(html_content, "html.parser")
        _normalize_wechat_code_styles(extract_root)
        extracted_md = trafilatura.extract(str(extract_root), output_format="markdown")
    else:
        html_content = _normalize_html_content(url, main_content)
        extracted_md = trafilatura.extract(html_content, output_format="markdown")

    content_text = main_content.get_text(" ", strip=True)
    if not content_text:
        raise ValueError("保存的 HTML 正文为空，未导入。")
    extracted_md = extracted_md or content_text

    return {
        "title": _normalize_title(title),
        "extracted_md": extracted_md,
        "html_content": html_content,
        "cover_image_url": cover_image_url,
        "account_name": account_name,
        "publish_time": publish_time,
    }


def _find_main_content(url: str, soup: BeautifulSoup) -> Tag | None:
    if "mp.weixin.qq.com" in url:
        return soup.find("div", {"id": "js_content"})
    if "csdn.net" in url:
        return soup.find("div", {"id": "article_content"})
    if "cnblogs.com" in url:
        return soup.find("div", {"id": "cnblogs_post_body"})
    return soup.find("article") or soup.find("main")


async def fetch_article_html(url: str, update_step):
    if "csdn.net" in url:
        update_step("正在通过浏览器引擎抓取 CSDN 网页...")
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = await context.new_page()
                await page.goto(url, timeout=30000)
                await page.wait_for_selector("#article_content", timeout=15000)
                html = await page.content()
                await browser.close()
                return html
        except Exception:
            pass

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    if "csdn.net" in url:
        headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
        headers["Accept-Language"] = "zh-CN,zh;q=0.9,en;q=0.8"

    async with httpx.AsyncClient(headers=headers, follow_redirects=True, verify=False, timeout=30.0, http2=True) as http_client:
        res = await http_client.get(url)
        return res.text


def extract_main_html(url: str, soup: BeautifulSoup) -> str:
    main_content = _find_main_content(url, soup)

    if not main_content:
        return ""

    if "mp.weixin.qq.com" in url and isinstance(main_content, Tag):
        _normalize_wechat_code_styles(main_content)

    return _normalize_html_content(url, main_content)


def _normalize_html_content(url: str, main_content: Tag) -> str:
    """Keep source layout while fixing lazy images and unsafe code styles."""
    html_content = str(main_content)
    html_content = re.sub(r"data-src\s*=", "src=", html_content, flags=re.IGNORECASE)
    html_content = re.sub(r"visibility:\s*hidden;?", "visibility: visible;", html_content, flags=re.IGNORECASE)
    html_content = re.sub(r'id="js_content"[^>]*style="[^"]*"', 'id="js_content"', html_content, flags=re.IGNORECASE)

    if "csdn.net" in url:
        html_content = re.sub(r'<div class="hide-article-box[^>]*>.*?</div>', "", html_content, flags=re.IGNORECASE | re.DOTALL)
        html_content = re.sub(r'<div class="hide-preCode-box[^>]*>.*?</div>', "", html_content, flags=re.IGNORECASE | re.DOTALL)
        html_content = re.sub(r"set-code-hide", "", html_content, flags=re.IGNORECASE)

    return html_content
