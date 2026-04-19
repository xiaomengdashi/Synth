from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
import uuid
import asyncio
from openai import AsyncOpenAI

router = APIRouter()

class ModelConfig(BaseModel):
    modelName: str
    apiKey: str
    baseUrl: str
    biliSessdata: str | None = None
    biliJct: str | None = None
    biliBuvid3: str | None = None

class TaskSubmit(BaseModel):
    url: str
    config: ModelConfig

# 模拟内存数据库
TASKS_DB = {}
ARTICLES_DB = {}

async def process_task(task_id: str, url: str, config: ModelConfig):
    import yt_dlp
    import httpx
    import trafilatura
    from bs4 import BeautifulSoup
    import urllib.parse
    
    # 区分视频与文章链接
    is_video = any(domain in url for domain in ['bilibili.com', 'douyin.com', 'youtube.com', 'b23.tv'])
    is_twitter = any(domain in url for domain in ['x.com', 'twitter.com'])
    
    try:
        client = AsyncOpenAI(
            api_key=config.apiKey,
            base_url=config.baseUrl
        )

        if is_twitter:
            TASKS_DB[task_id]["current_step"] = "正在尝试获取推文信息..."
            
            import urllib.request
            import json
            import ssl
            import subprocess
            
            api_url = url.replace("x.com", "api.vxtwitter.com").replace("twitter.com", "api.vxtwitter.com")
            api_url = api_url.split('?')[0]
            
            import subprocess
            import json
            
            try:
                # 为了解决各种 Python SSL 和代理的疑难杂症，直接使用系统底层的 curl 进行请求
                result = subprocess.run(['curl', '-s', '-k', '-L', api_url], capture_output=True, text=True, timeout=30)
                if result.returncode != 0:
                    raise Exception(f"主节点 curl 失败 (code {result.returncode}): stdout={result.stdout[:50]}, stderr={result.stderr}")
                tweet_data = json.loads(result.stdout)
                if 'error' in tweet_data or ('code' in tweet_data and tweet_data['code'] != 200):
                     raise Exception(f"API 返回错误: {tweet_data}")
            except Exception as req_e:
                import traceback
                print("REQ ERROR", traceback.format_exc())
                try:
                    backup_url = api_url.replace("api.vxtwitter.com", "api.fxtwitter.com")
                    result_backup = subprocess.run(['curl', '-s', '-k', '-L', backup_url], capture_output=True, text=True, timeout=30)
                    if result_backup.returncode != 0:
                        raise Exception(f"备用节点 curl 失败: {result_backup.stderr}")
                    tweet_data = json.loads(result_backup.stdout)
                    if 'error' in tweet_data or ('code' in tweet_data and tweet_data['code'] != 200):
                         raise Exception(f"API 返回错误: {tweet_data}")
                except Exception as backup_e:
                    try:
                        backup_url_2 = api_url.replace("api.vxtwitter.com", "api.twittpr.com")
                        result_final = subprocess.run(['curl', '-s', '-k', '-L', backup_url_2], capture_output=True, text=True, timeout=30)
                        if result_final.returncode != 0:
                            raise Exception(f"终极节点 curl 失败: {result_final.stderr}")
                        tweet_data = json.loads(result_final.stdout)
                        if 'error' in tweet_data or ('code' in tweet_data and tweet_data['code'] != 200):
                             raise Exception(f"API 返回错误: {tweet_data}")
                    except Exception as final_e:
                        raise Exception(f"无法获取推文信息 (所有节点均失败): 主节点:{req_e} | 备用节点:{backup_e} | 终极节点:{final_e}")
                
            author_name = tweet_data.get("user_name", "未知作者")
            
            # fxtwitter 返回的数据结构通常在 'tweet' 字段里
            if "tweet" in tweet_data:
                tweet_info = tweet_data["tweet"]
                author_name = tweet_info.get("author", {}).get("name", author_name)
                tweet_text = tweet_info.get("text", "")
                media = tweet_info.get("media", {})
                media_urls = [m.get("url") for m in media.get("photos", [])] + [m.get("url") for m in media.get("videos", [])]
                
                # 兼容旧结构检查
                title = f"{author_name} 的推文"
                if "article" in tweet_data and tweet_data["article"]:
                    title = tweet_data["article"].get("title", title)
            else:
                tweet_text = tweet_data.get("text", "")
                media_urls = tweet_data.get("mediaURLs", [])
                title = f"{author_name} 的推文"
                if "article" in tweet_data and tweet_data["article"]:
                    title = tweet_data["article"].get("title", title)
            
            # 防御性处理：确保 title 存在且合法
            if not title:
                title = "推文内容"
            
            TASKS_DB[task_id]["current_step"] = f"解析成功。正在调用 LLM 进行总结..."
            
            # 使用大模型翻译/总结
            prompt = f"请为以下推文（Tweet）生成一篇简短的 Markdown 资讯文章。\n\n作者：{author_name}\n内容：{tweet_text}\n\n要求：\n1. 如果有引用的文章(Article)内容，请重点关注。\n2. 提取核心观点。\n3. 如果内容是外语，请翻译为中文。\n4. 使用 Markdown 格式。\n5. 开头包含一段简短的摘要。\n\n"
            if "article" in tweet_data and tweet_data["article"]:
                prompt += f"附带的文章预览：\n标题：{tweet_data['article'].get('title', '')}\n摘要：{tweet_data['article'].get('preview_text', '')}\n"
            
            # 如果是推文，默认设置为空，稍后再覆盖
            html_content = ""
            extracted_md = ""
            
            response = await client.chat.completions.create(
                model=config.modelName,
                messages=[
                    {"role": "system", "content": "你是一个专业的科技资讯编辑，擅长翻译和总结推文内容。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=1000
            )
            
            generated_content = response.choices[0].message.content
            
            summary = "推文内容总结"
            if "摘要" in generated_content:
                summary_start = generated_content.find("摘要")
                summary = generated_content[summary_start:summary_start+100] + "..."
                
            # 将推文中的图片附在文章末尾
            if media_urls:
                generated_content += "\n\n### 附图\n\n"
                for m_url in media_urls:
                    generated_content += f"![推文配图]({m_url})\n"
            
            cover_image_url = media_urls[0] if media_urls else ""
            if "article" in tweet_data and tweet_data["article"].get("image"):
                cover_image_url = tweet_data["article"]["image"]

        elif is_video:
            TASKS_DB[task_id]["current_step"] = "正在通过专用接口解析视频信息..."
            
            # Bilibili 经常对海外 IP 返回 412，所以这里使用一个备用的解析方式 (通过第三方代理或通过 bs4)
            if 'bilibili.com' in url or 'b23.tv' in url:
                import re
                import json
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                }
                
                # 从请求中读取前端传来的 B 站 Cookie 身份认证（解决被拦截、无法获取 AI 字幕的问题）
                cookies = {}
                if config.biliSessdata:
                    cookies['SESSDATA'] = config.biliSessdata
                if config.biliJct:
                    cookies['bili_jct'] = config.biliJct
                if config.biliBuvid3:
                    cookies['buvid3'] = config.biliBuvid3
                
                async with httpx.AsyncClient(headers=headers, cookies=cookies, verify=False, follow_redirects=True, timeout=30.0) as http_client:
                    # 提取 bvid
                    bvid_match = re.search(r'BV[0-9A-Za-z]{10}', url)
                    if not bvid_match:
                        raise Exception("无法从链接中提取 BVID")
                    bvid = bvid_match.group(0)
                    
                    # 调用 Bilibili 官方开放 API (该接口通常不会返回 412)
                    api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
                    res = await http_client.get(api_url)
                    data = res.json()
                    if data.get('code') != 0:
                        raise Exception(f"Bilibili API 错误: {data.get('message')}")
                    
                    video_data = data['data']
                    title = video_data.get('title', '未知标题')
                    description = video_data.get('desc', '')
                    uploader = video_data.get('owner', {}).get('name', '未知作者')
                    
                    # 获取字幕
                    cid = video_data.get('cid')
                    transcript_text = ""
                    if cid:
                        TASKS_DB[task_id]["current_step"] = "正在尝试获取视频文稿/字幕..."
                        subtitle_api_url = f"https://api.bilibili.com/x/player/v2?bvid={bvid}&cid={cid}"
                        sub_res = await http_client.get(subtitle_api_url)
                        sub_data = sub_res.json()
                        if sub_data.get('code') == 0:
                            subtitles = sub_data.get('data', {}).get('subtitle', {}).get('subtitles', [])
                            if subtitles:
                                target_sub = next((s for s in subtitles if s.get('lan') == 'zh-CN'), subtitles[0])
                                sub_url = target_sub.get('subtitle_url')
                                if sub_url:
                                    if sub_url.startswith('//'):
                                        sub_url = 'https:' + sub_url
                                    sub_content_res = await http_client.get(sub_url)
                                    sub_content_data = sub_content_res.json()
                                    if 'body' in sub_content_data:
                                        transcript_text = " ".join([item.get('content', '') for item in sub_content_data['body']])
                    
            else:
                # 其他视频网站保留 yt-dlp 逻辑
                TASKS_DB[task_id]["current_step"] = "正在通过 yt-dlp 解析视频信息..."
                ydl_opts = {
                    'quiet': True, 
                    'simulate': True,
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    }
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    title = info.get('title', '未知标题')
                    description = info.get('description', '')
                    uploader = info.get('uploader', '未知作者')
                
            TASKS_DB[task_id]["current_step"] = f"解析成功: {title}。正在调用 LLM 进行总结..."
            
            # 2. 调用大模型
            html_content = ""
            # 对于其他视频站，初始化 transcript_text 为空，如果是 B站则前面已经赋了值
            if 'transcript_text' not in locals():
                transcript_text = ""
                
            extracted_md = transcript_text
            
            prompt = f"""
请你作为一位专业的 AI 资讯编辑，根据以下视频信息，写一篇结构清晰、吸引人的 Markdown 格式的资讯文章。

视频标题：{title}
视频作者：{uploader}
视频简介/详情：
{description}
"""
            if transcript_text:
                # 安全截断长文本 (最大保留约25000字)，且尽量在句号等标点处截断，避免乱码
                max_len = 25000
                if len(transcript_text) > max_len:
                    # 寻找 max_len 附近最后的句号、叹号或问号
                    cut_idx = max_len
                    for punct in ['。', '！', '？', '.', '!', '?']:
                        idx = transcript_text.rfind(punct, max_len - 500, max_len)
                        if idx != -1 and idx > cut_idx - 500:
                            cut_idx = idx + 1
                    transcript_text = transcript_text[:cut_idx] + "\n\n...(部分文稿过长已截断)..."
                
                prompt += f"\n视频文稿/字幕内容：\n{transcript_text}\n"
            else:
                prompt += f"\n(注：未获取到该视频的详细文稿，请根据标题和简介进行总结)\n"

            prompt += """
要求：
1. 仔细阅读视频文稿内容，提炼出真正的核心观点和重要细节。
2. 分点列出内容，语言需要专业、简练，适合科技和 AI 领域的读者。
3. 必须使用 Markdown 格式（包含合适的标题、引用、无序/有序列表等）。
4. 在文章开头需要有一段简短的摘要。
            """

            response = await client.chat.completions.create(
                model=config.modelName,
                messages=[
                    {"role": "system", "content": "你是一个专业的科技资讯编辑，擅长将零散的视频信息总结为高质量的文章。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1500
            )
            
            generated_content = response.choices[0].message.content
            
            summary = "由 AI 自动生成的内容摘要。"
            # 从生成的文本中提取摘要（简单截取）
            if "摘要" in generated_content:
                summary_start = generated_content.find("摘要")
                summary = generated_content[summary_start:summary_start+100] + "..."
                
        else:
            # 文章处理流程
            TASKS_DB[task_id]["current_step"] = "正在抓取公众号/文章内容..."
            
            html = ""
            
            # CSDN 经常会返回包含混淆 JS 的 412 拦截页面
            # 为了稳定绕过阿里云 WAF 的反爬机制，使用 Playwright 驱动真实浏览器抓取
            if 'csdn.net' in url:
                TASKS_DB[task_id]["current_step"] = "正在通过浏览器引擎抓取 CSDN 网页..."
                from playwright.async_api import async_playwright
                try:
                    async with async_playwright() as p:
                        browser = await p.chromium.launch(headless=True)
                        context = await browser.new_context(
                            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        )
                        page = await context.new_page()
                        await page.goto(url, timeout=30000)
                        # 等待文章正文加载，代表已经突破了反爬重定向
                        await page.wait_for_selector('#article_content', timeout=15000)
                        html = await page.content()
                        await browser.close()
                except Exception as e:
                    import traceback
                    print("CSDN Playwright Error:", traceback.format_exc())
                    # 如果 Playwright 失败，降级使用普通请求
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
                    }
                    async with httpx.AsyncClient(headers=headers, verify=False, follow_redirects=True, timeout=30.0) as http_client:
                        res = await http_client.get(url)
                        html = res.text
            else:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
                # 使用 httpx 异步请求
                async with httpx.AsyncClient(headers=headers, follow_redirects=True, verify=False, timeout=30.0, http2=True) as http_client:
                    res = await http_client.get(url)
                    html = res.text
            
            # 使用 BeautifulSoup 获取标题
            soup = BeautifulSoup(html, 'html.parser')
            title = soup.title.string if soup.title else "未知文章标题"
            # 针对微信公众号特殊处理标题和封面
            cover_image_url = ""
            if "mp.weixin.qq.com" in url:
                og_title = soup.find("meta", property="og:title")
                if og_title and og_title.get("content"):
                    title = og_title["content"]
                
                # 尝试获取微信公众号封面图
                og_image = soup.find("meta", property="og:image")
                if og_image and og_image.get("content"):
                    cover_image_url = og_image["content"]
            elif 'csdn.net' in url:
                title_tag = soup.find('h1', class_='title-article')
                if title_tag:
                    title = title_tag.get_text(strip=True)
            elif 'cnblogs.com' in url:
                title_tag = soup.find('span', role='heading')
                if title_tag:
                    title = title_tag.get_text(strip=True)
                else:
                    title_tag = soup.find('a', id='cb_post_title_url')
                    if title_tag:
                        title = title_tag.get_text(strip=True)

            TASKS_DB[task_id]["current_step"] = f"抓取成功: {title}。正在解析正文并生成摘要..."
            
            # 使用 trafilatura 提取 Markdown 正文
            extracted_md = trafilatura.extract(html, output_format="markdown")
            if not extracted_md:
                extracted_md = "> 无法提取文章正文，可能是该网站不支持自动抓取。"
            
            # 暂存 html 到 markdown，前端如果发现有 <!-- HTML_CONTENT_START --> 标记，可以渲染为 HTML
            import re
            html_content = ""
            
            # 精确提取各平台的文章主体内容容器，避免引入侧边栏、评论区等无关 DOM 导致排版崩坏
            main_content = None
            if "mp.weixin.qq.com" in url:
                main_content = soup.find('div', {'id': 'js_content'})
            elif "csdn.net" in url:
                main_content = soup.find('div', {'id': 'article_content'})
            elif "cnblogs.com" in url:
                main_content = soup.find('div', {'id': 'cnblogs_post_body'})
            
            if main_content:
                html_content = str(main_content)
                # 清洗 HTML 以适配前端渲染
                html_content = re.sub(r'data-src\s*=', 'src=', html_content, flags=re.IGNORECASE)
                html_content = re.sub(r'visibility:\s*hidden;?', 'visibility: visible;', html_content, flags=re.IGNORECASE)
                html_content = re.sub(r'id="js_content"[^>]*style="[^"]*"', 'id="js_content"', html_content, flags=re.IGNORECASE)
                
                # CSDN 专属样式清洗（移除展开更多按钮等干扰元素，修复代码块显示）
                if "csdn.net" in url:
                    html_content = re.sub(r'<div class="hide-article-box[^>]*>.*?</div>', '', html_content, flags=re.IGNORECASE | re.DOTALL)
                    html_content = re.sub(r'<div class="hide-preCode-box[^>]*>.*?</div>', '', html_content, flags=re.IGNORECASE | re.DOTALL)
                    html_content = re.sub(r'set-code-hide', '', html_content, flags=re.IGNORECASE)
            else:
                # 如果没有匹配到任何特定平台的文章容器，则清空 html_content，强制前端使用高质量的 Markdown 渲染
                html_content = ""
            
            # 使用大模型生成摘要
            prompt = f"请为以下文章生成一段简短的摘要（50-100字），只输出摘要文字即可：\n\n{extracted_md[:2000]}"
            
            response = await client.chat.completions.create(
                model=config.modelName,
                messages=[
                    {"role": "system", "content": "你是一个专业的科技资讯编辑，擅长总结文章核心内容。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=200
            )
            
            summary = response.choices[0].message.content.strip()
            
            if html_content:
                generated_content = f"## 摘要\n\n{summary}\n\n---\n\n<!-- HTML_CONTENT_START -->\n{html_content}\n<!-- HTML_CONTENT_END -->"
            else:
                generated_content = f"## 摘要\n\n{summary}\n\n---\n\n{extracted_md}"

        # 统一处理完成状态
        TASKS_DB[task_id]["status"] = "completed"
        TASKS_DB[task_id]["current_step"] = "处理完成"
        
        # 3. 写入假文章 (TODO: 真实流程中写入数据库)
        article_id = str(uuid.uuid4())
        TASKS_DB[task_id]["article_id"] = article_id
        
        source_type = (
            'bilibili' if 'bilibili' in url or 'b23.tv' in url else
            'douyin' if 'douyin' in url else
            'wechat' if 'weixin' in url else
            'x' if ('x.com' in url or 'twitter.com' in url) else
            'csdn' if 'csdn.net' in url else
            'cnblogs' if 'cnblogs.com' in url else
            'other'
        )
        
        # 生成配图的 prompt
        img_prompt = urllib.parse.quote(f"Technology AI abstract {title[:10]}")
        
        # 如果是微信文章且成功抓取了封面，则使用原封面；如果是推文且抓取到了封面，则使用推文封面；否则使用 AI 生成
        if 'cover_image_url' in locals() and cover_image_url:
            final_cover_url = cover_image_url
        else:
            final_cover_url = f"https://coresg-normal.trae.ai/api/ide/v1/text_to_image?prompt={img_prompt}&image_size=landscape_16_9"
        
        article_data = {
            "id": article_id,
            "title": title,
            "summary": summary,
            "content_md": generated_content,
            "original_url": url,
            "source_type": source_type,
            "cover_image_url": final_cover_url,
            "created_at": TASKS_DB[task_id]["created_at"]
        }
        
        # 将生成的文章存入内存数据库
        TASKS_DB[task_id]["article"] = article_data
        ARTICLES_DB[article_id] = article_data
        
        # 存入 SQLite 数据库
        from app.database import AsyncSessionLocal
        from app.models import Article, Task as TaskModel
        import datetime
        
        async with AsyncSessionLocal() as session:
            # 保存文章
            db_article = Article(
                id=article_id,
                title=title,
                summary=summary,
                content_md=generated_content,
                original_url=url,
                source_type=source_type,
                cover_image_url=final_cover_url,
                created_at=datetime.datetime.fromisoformat(TASKS_DB[task_id]["created_at"])
            )
            session.add(db_article)
            
            # 更新/保存任务
            db_task = await session.get(TaskModel, task_id)
            if not db_task:
                db_task = TaskModel(
                    id=task_id,
                    original_url=url,
                    created_at=datetime.datetime.fromisoformat(TASKS_DB[task_id]["created_at"])
                )
                session.add(db_task)
            db_task.status = "completed"
            db_task.current_step = "处理完成"
            db_task.article_id = article_id
            
            await session.commit()
        
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        print(f"Task failed: {err_msg}")
        
        TASKS_DB[task_id]["status"] = "failed"
        TASKS_DB[task_id]["current_step"] = f"处理失败: {repr(e)}"
        
        # 将失败状态也存入数据库
        try:
            from app.database import AsyncSessionLocal
            from app.models import Task as TaskModel
            async with AsyncSessionLocal() as session:
                db_task = await session.get(TaskModel, task_id)
                if db_task:
                    db_task.status = "failed"
                    db_task.current_step = f"处理失败: {repr(e)}"
                    db_task.error_message = err_msg
                    await session.commit()
        except Exception as db_e:
            print(f"Failed to update task status in DB: {db_e}")

@router.post("/submit")
async def submit_task(data: TaskSubmit, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    import datetime
    
    # 初始化内存任务状态
    TASKS_DB[task_id] = {
        "id": task_id,
        "original_url": data.url,
        "status": "pending",
        "current_step": "任务已接收",
        "article_id": None,
        "created_at": datetime.datetime.now().isoformat()
    }
    
    # 初始化 SQLite 任务状态
    from app.database import AsyncSessionLocal
    from app.models import Task as TaskModel
    try:
        async with AsyncSessionLocal() as session:
            new_db_task = TaskModel(
                id=task_id,
                original_url=data.url,
                status="pending",
                current_step="任务已接收",
                created_at=datetime.datetime.fromisoformat(TASKS_DB[task_id]["created_at"])
            )
            session.add(new_db_task)
            await session.commit()
    except Exception as e:
        print(f"Failed to create task in DB: {e}")
        
    background_tasks.add_task(process_task, task_id, data.url, data.config)
    return {"task_id": task_id, "status": "pending"}

@router.get("/{task_id}/status")
async def get_task_status(task_id: str):
    task = TASKS_DB.get(task_id)
    if not task:
        return {"error": "Task not found"}
    return task
