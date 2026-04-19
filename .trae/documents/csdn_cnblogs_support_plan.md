# 新增 CSDN 与 Cnblogs 文章解析支持的可行性及实施计划

## 1. 现状分析
当前 `Synth` 项目的后端主要支持处理以下几类链接：
- **推文 (Twitter/X)**：使用专门的 API 节点拉取并由 LLM 翻译/总结。
- **视频 (Bilibili/Douyin/YouTube)**：使用官方 API 或 `yt-dlp` 拉取元数据与字幕，由 LLM 总结。
- **普通文章 (包含微信公众号)**：使用 `httpx` 抓取 HTML，然后通过 `BeautifulSoup` 提取标题，使用 `trafilatura` 提取 Markdown 正文，最后由 LLM 生成摘要。

当前前端的 `source_type` 仅支持 `'wechat' | 'bilibili' | 'douyin' | 'x'`，其他未命中规则的链接在后端会被标记为 `'other'`，但在前端没有相应的完善展示逻辑。

## 2. CSDN 与 Cnblogs 解析的特点与挑战
- **CSDN (csdn.net)**：
  - 文章页通常包含大量广告、侧边栏、推荐阅读等干扰元素。
  - 代码块较多，需要保留代码的格式。
  - 可能存在反爬虫机制（需要 User-Agent 伪装）。
  - **可行性**：非常高。使用现有的 `trafilatura` 库通常能较好地从 CSDN 的 DOM 结构中提取出核心的 Markdown 正文，丢弃无关的侧边栏。我们只需在现有的“普通文章”处理逻辑中增加专门针对 CSDN 的标题提取和特征适配即可。
- **Cnblogs (博客园, cnblogs.com)**：
  - 页面结构相对传统和干净，主体内容通常位于特定的 ID 容器中（如 `#cnblogs_post_body`）。
  - 同样包含代码块。
  - **可行性**：非常高。现有的 `trafilatura` 提取效果通常很好。同样可以增加针对性的标题和正文提取优化。

## 3. 拟定实施方案

为了完美支持 CSDN 和 Cnblogs，计划在后端和前端分别进行以下修改：

### 3.1 后端修改 (`backend/app/routers/tasks.py`)
1. **URL 识别与路由**：
   - 现有的“普通文章处理流程”（处理 `is_video` 和 `is_twitter` 之外的 `else` 分支）已经非常适合处理博客文章。
   - 我们只需要在这个分支内，增加对 CSDN 和 Cnblogs 的特定处理。
2. **标题与内容提取优化**：
   - 在使用 `BeautifulSoup` 解析 HTML 后：
     - 如果 URL 包含 `csdn.net`，尝试从 `<h1 class="title-article">` 或类似特征提取更准确的标题。
     - 如果 URL 包含 `cnblogs.com`，尝试从 `<a id="cb_post_title_url">` 提取标题。
   - 继续使用 `trafilatura` 提取 Markdown 正文（这部分不需要改动，`trafilatura` 会自动处理 DOM 树）。
3. **`source_type` 判定**：
   - 修改 `tasks.py` 中的 `source_type` 生成逻辑，增加对 `csdn` 和 `cnblogs` 的识别：
     ```python
     source_type = (
         'bilibili' if 'bilibili' in url or 'b23.tv' in url else
         'douyin' if 'douyin' in url else
         'wechat' if 'weixin' in url else
         'x' if 'x.com' in url or 'twitter.com' in url else
         'csdn' if 'csdn.net' in url else
         'cnblogs' if 'cnblogs.com' in url else
         'other'
     )
     ```

### 3.2 前端修改
1. **类型定义 (`frontend/src/store/useStore.ts`)**：
   - 将 `source_type` 的类型扩展为 `'wechat' | 'bilibili' | 'douyin' | 'x' | 'csdn' | 'cnblogs' | 'other'`。
2. **图标与标签展示 (`frontend/src/pages/Home.tsx`)**：
   - 修改 `getSourceIcon` 函数，为 `csdn` 和 `cnblogs` 添加对应的图标（可以使用 Lucide 的 `Code`、`BookOpen` 或 `Terminal` 图标），并指定颜色（例如 CSDN 用红色，Cnblogs 用深蓝色）。
   - 修改 `getSourceLabel` 函数，添加中文字段映射（`'CSDN'` 和 `'博客园'`）。
3. **详情页展示 (`frontend/src/pages/Article.tsx`)**：
   - 现有的详情页逻辑直接使用了 `article.source_type.toUpperCase()`，这对于 `csdn` 和 `cnblogs` 同样适用，无需额外大改。

## 4. 预期效果
修改完成后，用户可以在控制台提交任意 CSDN 或 Cnblogs 的文章链接。系统会自动爬取页面，剥离广告和侧边栏，提取出干净的 Markdown 格式的代码和正文，并调用 LLM 生成摘要。同时，首页会显示醒目的“CSDN”或“博客园”专属标签和图标。

---
**实施确认**：
上述计划将确保 CSDN 和 Cnblogs 的文章被高质量解析，并在前端得到完美的展示。
不需要用户进行任何操作，请查阅计划并确认，确认后我将立即开始修改代码。