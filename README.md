# SynthAI - 自动化 AI 资讯聚合

SynthAI 是一个科技内容归档平台。它可以接收微信公众号、B站、YouTube 或推特（X）的链接，自动提取音视频和图文内容，并保存为适合阅读的 Markdown/HTML 文章。

## 项目结构

本项目采用前后端分离的架构：

- `frontend/`: 前端应用，基于 React 18 + Vite + TypeScript 构建。
  - 使用 Zustand 进行状态管理。
  - 使用 Tailwind CSS 进行样式开发。
  - 提供可视化的管理控制台，用于提交链接和配置大模型。
- `backend/`: 后端服务，基于 Python FastAPI 构建。
  - 使用 SQLite 存储文章和任务状态。
  - 集成了 `yt-dlp`、`trafilatura` 等抓取工具。
  - 保留 OpenAI 兼容服务参数设置，当前导入流程暂不调用大模型。

## 快速开始

### 1. 启动后端服务

首先，进入 `backend` 目录并激活本机统一虚拟环境 `~/venv`（若尚未创建，可先执行 `python3 -m venv ~/venv`）：

```bash
source ~/venv/bin/activate  # Windows 用户使用 %USERPROFILE%\venv\Scripts\activate
cd backend

# 安装依赖（首次或 requirements 变更后）
pip install -r requirements.txt

# 启动 FastAPI 服务
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

后端服务将在 `http://127.0.0.1:8000` 启动。

页面时间跟随部署服务器的系统时区（或运行环境的 `TZ` 设置）。数据库保存 UTC 时间，接口返回带偏移的本地时间，前台使用服务器提供的时区显示。

### 2. 启动前端服务

然后，进入 `frontend` 目录并启动开发服务器：

```bash
cd frontend

# 安装依赖
npm install  # 或 yarn install / pnpm install

# 启动前端开发服务器
npm run dev  # 或 yarn dev / pnpm dev
```

前端应用将在 `http://localhost:5173` 启动。

## 配置与使用

1. 打开浏览器访问前端地址（例如：`http://localhost:5173`）。
2. 进入**控制台**页面（`/admin`）。
3. 可在管理后台的**模型服务**页面保存 API Key、Base URL 以及模型名称参数（如 `gpt-4o-mini`）。这些参数将保存在后端 SQLite 数据库的 `app_settings` 表中，但当前导入流程不会调用模型。
4. 在**系统设置 → 内容获取**页面调整平台获取优先级，并按需填写 TikHub API Token（Bilibili 及 X、微信的 TikHub 方式需要）。
5. 在输入框中粘贴支持的链接（微信公众号、B站、推特、YouTube 等），点击**开始处理**。

### 内容抓取：按平台设置获取优先级

后台 `/admin/tikhub` 的「获取方式与优先级」面板按平台列出可用方式。使用上下按钮调整顺序并保存，新导入、分享导入、X 预览和「重新获取」均读取服务端保存的顺序；前一种获取失败或返回空正文时自动回退。已在处理中的任务使用提交时的配置。

X 的 **X GraphQL** 方法直接请求 X 网页公开的 `TweetResultByRestId` 操作（不是官方开发者 API），获取完整 Article JSON，并将 Draft.js 的段落、标题、嵌套列表、行内格式及 atomic 媒体渲染为 HTML。按 `media_entities` 与封面 URL 下载图片、GIF（X 通常以 MP4 提供）和视频，保存到 `backend/data/media/x/<推文ID>/media/`，HTML 正文随文章记录入库并由文章库阅读页统一展示；不生成独立 HTML 页面，`/media/x/` 仅提供图片、视频及字体资源。失败资源会显示明确警告，不把缺失媒体伪装为完整成功。复用后台「X 登录配置」保存的 `auth_token` 与 `ct0`，无需安装 twitter-cli，也不读取浏览器 Cookie。旧 X Content Downloader／yt-dlp 方法已删除，已保存的优先级会原位迁移为 X GraphQL；微信公众号的 Content Downloader 不变。

微信公众号也支持 **Content Downloader**：复用 `content-downloader` 的 `WeChatOAParser` 公开网页请求方式，使用 30 秒超时和浏览器请求头直接获取 HTML，无需 TikHub Key 或登录态。提取完整的嵌套 `#js_content` 正文、公众号名、发布时间与封面，保留原排版、代码换行、图片地址及语音标签；图片由现有微信阅读视图按原地址加载。验证页、失效页和空正文不会作为文章保存，自动回退下一种方式。

X 还提供可选的 **twitter-cli**：恢复历史中的 X 登录态读取路径，优先通过 CLI 的 Python 运行环境调用 `TweetResultByRestId` 获取长文 Draft.js 富文本和图片；无法读取富文本时尝试 `twitter article <宿主推文链接> --markdown`。正文交给现有 X 阅读视图展示，获取失败继续尝试下一种方式。需要在**运行后端的服务器**安装 twitter-cli，然后在后台 **系统设置 → X 登录配置** 填写同一账号的 `auth_token` 和 `ct0`，可选填写 CLI 可执行文件路径。保存后下次抓取立即生效，无需重启；后台凭据仅保存在服务端 SQLite，读取接口只返回掩码和配置状态。也可在服务环境或 `backend/.backend.env` 中配置 `TWITTER_AUTH_TOKEN`、`TWITTER_CT0` 及可选的 `SYNTHAI_TWITTER_BIN`（修改环境变量后需重启）。后台保存的凭据优先于环境变量，清除后恢复环境变量回退；路径单独按后台配置、环境变量、系统 PATH 的顺序查找。凭据仅传入子进程环境，不放在命令参数中。未配置显式凭据时不会启动 CLI，也不会自动提取浏览器 Cookie。配置接口为受后台令牌保护的 `GET/PUT/DELETE /api/v1/config/twitter-cli`；PUT 接受 `authToken`、`ct0`、`executable`，凭据留空保持现值，DELETE 仅清除后台保存的凭据。后台会显示安装和配置状态；配置齐全不代表登录态已验证有效。点击「验证 X 登录态」会通过 `POST /api/v1/config/twitter-cli/verify` 使用已保存的配置请求 X 当前登录账号，返回验证结果、时间和当前账号的显示名称、用户名；不会回退到其他提供方，不会返回凭据或其他账号资料。验证结果只反映本次请求，修改配置后需重新验证。仍需提供宿主推文链接，不支持 `i/article` 直链。

X 默认顺序为 **TikHub → Content Downloader → twitter-cli**，微信为 **TikHub → Content Downloader**；新增方式自动追加到已有顺序末尾，不覆盖原先的排序。两平台独立排序，如需优先使用某一方式，可将它上移并保存。Bilibili 和普通网页目前各有一种方式，后续增加提供方后可使用同一排序设置。优先级存于 SQLite，不会被模型、网络等其他设置的保存覆盖。所有方式均失败时任务显示各方式的失败原因；重新获取失败保留原文章。

现有 [TikHub](https://docs.tikhub.io) 接口如下：

| 平台 | TikHub 接口 | 说明 |
|---|---|---|
| X/Twitter | `twitter/web/fetch_tweet_detail` | 推文、长推文、X 长文全文（长文为纯文本，TikHub 不返回内嵌图片） |
| 微信公众号 | `wechat_mp/v2/fetch_article_detail_h5`（POST） | 完整正文 HTML（内嵌图片保留），绕过微信安全验证 |
| Bilibili | `bilibili/web/fetch_video_parts` + `bv_to_aid` + `fetch_one_video_v2` | 分P列表 + 中文字幕文稿；TikHub 的 view 类接口不可用，UP主/封面/简介缺失 |

当前首页来源选择、文章库筛选、手机分享与获取优先级已接入以下平台：

| 来源 | 获取方式 | 保存内容与要求 |
|---|---|---|
| CSDN | 网页直取，必要时使用 Playwright | 正文、代码、图片；需要安装 Playwright Chromium 才能使用浏览器回退 |
| 博客园 | 网页直取 | 专用正文区域、代码、图片 |
| 其他公开网页 | HTTP + 正文提取 | Markdown 或正文 HTML；登录、付费或验证页面不保证可获取 |
| YouTube | yt-dlp → TikHub（可调顺序） | 人工/自动字幕，无字幕时下载音频转写；支持 watch、youtu.be、Shorts 链接 |

视频获取必须返回有效文稿；仅有视频标题和简介时任务报错，不会伪装成已获取完整正文。已有字幕不会调用语音转写；模型未配置或笔记生成失败时保存原文稿。没有字幕时使用后台「语音转写」配置的 MiniMax Key，临时音频在处理后自动删除。

部署安装：`pip install -r backend/requirements.txt`；音频转写需 `ffmpeg`（Ubuntu：`sudo apt install ffmpeg`）。YouTube 的 yt-dlp 路径需提供 [Node.js 22+ 或 Deno 2.3+](https://github.com/yt-dlp/yt-dlp/wiki/EJS)；依赖中包含 yt-dlp 的 EJS 组件，不从浏览器自动提取登录 Cookie。部署脚本会在 Ubuntu 缺少 ffmpeg 时安装它。需要浏览器抓取 CSDN 时运行 `python -m playwright install --with-deps chromium`。后台「获取优先级」的对应平台下会显示部署依赖摘要，展开可查看适用场景、服务器安装命令、官方文档及配置入口；无额外系统软件要求的平台也会明确注明。

「系统设置 → 网络配置 → 视频下载代理」用于视频媒体下载，沿用 `bilibiliProxy` 存储字段及 `BILIBILI_PROXY` 环境变量；TikHub API 请求仍使用单独的接口端点。平台风控、地域或服务器网络限制可能导致媒体下载失败，届时任务显示具体失败原因，可配置代理后重新获取。

配置方式：进入管理后台 `/admin/tikhub?section=account`，保存 API Token（先验证有效性，存储在后端 SQLite `app_settings` 表）。服务器部署后也在此页面设置一次即可。


Token 在 [user.tikhub.io](https://user.tikhub.io) 用户控制台创建并充值。TikHub 按次计费：X 推文 1 次/条，微信文章 1 次/篇，B站视频约 3 次/条（分P + aid 转换 + 字幕）。余额不足（402）时任务会失败并提示充值，微信文章仍可通过首页的 **导入网页 HTML** 手动导入（需包含 `#js_content` 节点）。

注意：`x.com/i/article/...` 形式的长文直链暂不支持（TikHub 仅支持推文链接），请使用宿主推文的链接。

### iPhone 分享导入

项目已内置一条 iPhone 分享链路，适合在手机上浏览 X 或微信文章时顺手保存：

1. 在网站中打开 `分享导入` 设置页，也就是前端的 `/share/setup`。
2. 前端部署时可配置 `VITE_SHARE_SHORTCUT_ICLOUD_URL`，让页面优先显示 `iCloud 快捷指令` 一键安装入口；示例见 `frontend/.env.example`。
3. 在 iPhone 上打开该 iCloud 链接并导入 `保存到 SynthAI`，把网站地址改成手机可访问的域名或局域网地址。
4. 如果暂时没有配置 iCloud 链接，也可以在 `/share/setup` 页面按提示手动创建快捷指令。
5. 在 X App 或微信中打开文章，点击分享，选择 `保存到 SynthAI`。
6. 网站会跳转到 `/share?text=...`，自动提取分享里的文章链接，创建任务，并在抓取完成后打开文章详情页。

分享导入接收微信、X、B 站、YouTube、CSDN、博客园及公开网页链接；YouTube 短链与标准视频链接会归并为同一任务。X 转发外部文章时仍优先尝试抓取原网页。

## 技术栈

**Frontend:** React, TypeScript, Vite, Tailwind CSS, Zustand, React Router, Framer Motion
**Backend:** Python, FastAPI, SQLAlchemy, SQLite, OpenAI Python SDK, yt-dlp, trafilatura, BeautifulSoup4

### TikHub 账户与多平台查询

- `/admin/settings?tab=tikhub`：验证并保存/更换 Key、移除页面保存的 Key、查看余额/免费额度、Key 权限与有效期、今日用量及接口调用明细。Key 仅保存在服务端 SQLite，不再支持环境变量，也不会返回给前端。
- `/admin/tikhub/query`：21 个分类、690 个查询接口，支持平台筛选、接口搜索、分页、动态参数表单、字段/JSON 结果视图、复制和 JSON 导出。包含 TikHub 账户与计费，以及 TikTok、小红书、B站、X、微信、YouTube、Instagram、快手、微博、知乎等内容查询。
- “账户与计费”分类包含用户信息、每日用量、端点信息、所有端点信息、阶梯折扣与价格估算。上游每日用量接口没有日期参数，页面显示 TikHub 返回的统计日期，不提供虚构的历史日期筛选。
- Key 只由后端保存和使用。通用配置接口只返回 `tikhubConfigured`，不会返回 TikHub Key；旧版浏览器提交的 `tikhubApiKey` 不再覆盖后端 Key。首页导入、分享导入与 X 预览也使用后端配置。
- 查询需要 Key 具有对应权限及足够额度，部分接口另外需要平台 Cookie 等参数。所有请求都由用户点击触发，不批量自动执行或自动重试计费请求。账号信息可查询不代表所有平台接口均已授权。
- 接口来自官方 OpenAPI 快照，查询后端只允许目录中的路径与方法，校验参数类型、必填项和范围；未接入注册设备、生成签名等非查询工具。结果中的超长整数转为字符串，避免 JavaScript 丢失 ID 精度；结果按文本展示，不执行上游 HTML。

新增/完善的后端接口：

| 接口 | 用途 |
| --- | --- |
| `GET /api/v1/tikhub/key` | 脱敏 Key、配置来源与状态 |
| `POST /api/v1/tikhub/key` | `{ "apiKey": "..." }`，验证成功后保存 |
| `DELETE /api/v1/tikhub/key` | 移除页面保存的 Key，保留环境变量回退 |
| `GET /api/v1/tikhub/account` | 账户摘要和每日用量；用量失败返回独立警告 |
| `GET /api/v1/tikhub/catalog` | `platform`、`q`、`offset`、`limit` 筛选查询目录 |
| `POST /api/v1/tikhub/query` | `{ "endpoint_id": "GET /api/v1/twitter/web/fetch_tweet_detail", "parameters": { "tweet_id": "1808168603721650364" } }` |

目录保存在 `backend/app/data/tikhub_catalog.json`，服务运行时不依赖文档站。官方接口更新后可手动重新生成并验证：

```bash
curl --fail https://api.tikhub.io/openapi.json -o /tmp/tikhub-openapi.json
python backend/scripts/build_tikhub_catalog.py /tmp/tikhub-openapi.json
cd backend
python -m pytest
```

更新后需安装 `backend/requirements.txt` 中的依赖并重启后端。现有系统未提供管理员登录，部署时应在反向代理层限制管理页面及 `/api/v1/config`、`/api/v1/tikhub` 等管理接口的访问。
