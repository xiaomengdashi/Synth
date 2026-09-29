# SynthAI - 自动化 AI 资讯聚合

SynthAI 是一个科技内容归档平台。它可以接收微信公众号、B站、抖音或推特（X）的链接，自动提取音视频和图文内容，并保存为适合阅读的 Markdown/HTML 文章。

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
4. 在**系统配置 → TikHub 抓取**页面填写 TikHub API Token（必填，见下节）。
5. 在输入框中粘贴支持的链接（微信公众号、B站、推特、抖音、YouTube 等），点击**开始处理**。

### 内容抓取：统一走 TikHub 第三方接口

X/Twitter（推文与长文）、微信公众号文章、Bilibili 视频的抓取统一通过 [TikHub](https://docs.tikhub.io) 第三方接口完成，无需任何本机登录态或浏览器：

| 平台 | TikHub 接口 | 说明 |
|---|---|---|
| X/Twitter | `twitter/web/fetch_tweet_detail` | 推文、长推文、X 长文全文（长文为纯文本，TikHub 不返回内嵌图片） |
| 微信公众号 | `wechat_mp/v2/fetch_article_detail_h5`（POST） | 完整正文 HTML（内嵌图片保留），绕过微信安全验证 |
| Bilibili | `bilibili/web/fetch_video_parts` + `bv_to_aid` + `fetch_one_video_v2` | 分P列表 + 中文字幕文稿；TikHub 的 view 类接口不可用，UP主/封面/简介缺失 |

抖音、YouTube 等其他视频链接仍通过 yt-dlp 解析；CSDN、cnblogs 及普通网页仍走内置网页抓取。

配置方式（二选一，推荐在管理后台填写）：

1. 管理后台填写：进入 `/admin/settings/tikhub`，保存 API Token（先验证有效性，存储在后端 SQLite `app_settings` 表；`data/config.json` 若存在会在启动时自动迁移）。
2. 环境变量：部署机器上设置 `TIKHUB_API_TOKEN`。

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

当前这条链路默认接收的是 `x.com` / `twitter.com` 的帖子或 X 长文链接，以及 `mp.weixin.qq.com` 的微信公众号文章链接；如果是 X 里转发出去的外部网页，也会优先尝试抓取原网页正文。

## 技术栈

**Frontend:** React, TypeScript, Vite, Tailwind CSS, Zustand, React Router, Framer Motion
**Backend:** Python, FastAPI, SQLAlchemy, SQLite, OpenAI Python SDK, yt-dlp, trafilatura, BeautifulSoup4

### TikHub 账户与多平台查询

- `/admin/settings/tikhub`：验证并保存/更换 Key、移除页面保存的 Key、查看余额/免费额度、Key 权限与有效期、今日用量及接口调用明细。保存的 Key 优先于 `TIKHUB_API_TOKEN`；移除后若存在环境变量则自动使用环境变量。
- `/admin/tikhub/query`：23 个分类、996 个查询接口，支持平台筛选、接口搜索、分页、动态参数表单、字段/JSON 结果视图、复制和 JSON 导出。包含 TikHub 账户与计费，以及抖音、TikTok、小红书、B站、X、微信、YouTube、Instagram、快手、微博、知乎等内容查询。
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
