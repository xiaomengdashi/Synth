import re

import httpx
import trafilatura
from bs4 import BeautifulSoup, Tag
from app.config import settings
from app.services.fetchers.wechat_browser import fetch_wechat_article_html, is_wechat_blocked_page


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


async def fetch_article_content(url: str, update_step):
    update_step("正在抓取公众号/文章内容...")
    html = await fetch_article_html(url, update_step)
    result = parse_article_html(url, html)

    update_step(f"抓取成功: {result['title']}。正在解析正文并保存内容...")
    return result


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

    if "mp.weixin.qq.com" in url and isinstance(main_content, Tag):
        _normalize_wechat_code_styles(main_content)
    html_content = _normalize_html_content(url, main_content)
    content_text = main_content.get_text(" ", strip=True)
    if not content_text:
        raise ValueError("保存的 HTML 正文为空，未导入。")
    extracted_md = trafilatura.extract(html_content, output_format="markdown") or content_text

    return {
        "title": _normalize_title(title),
        "extracted_md": extracted_md,
        "html_content": html_content,
        "cover_image_url": cover_image_url,
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
        html = res.text
        if "mp.weixin.qq.com" in url:
            soup = BeautifulSoup(html, "html.parser")
            content = soup.find("div", {"id": "js_content"})
            content_text = content.get_text(" ", strip=True) if content else ""
            if is_wechat_blocked_page(str(res.url), html) or len(content_text) < 120:
                if settings.WECHAT_BROWSER_ENABLED:
                    update_step("普通请求被微信拦截，正在切换浏览器读取...")
                    return await fetch_wechat_article_html(url, update_step)
                raise RuntimeError(
                    "微信返回安全验证页，当前已关闭自动浏览器读取。"
                    "请在可打开文章的环境中保存网页 HTML，再使用 HTML 导入。"
                )
        return html


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
