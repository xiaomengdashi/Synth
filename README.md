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
3. 可在管理后台的**模型服务**页面保存 API Key、Base URL 以及模型名称参数（如 `gpt-4o-mini`）。这些参数将保存在后端的 `data/config.json` 中，但当前导入流程不会调用模型。
4. 在输入框中粘贴支持的链接（微信公众号、B站、推特等），点击**开始处理**。
5. 系统将在后台自动拉取并保存原文。微信触发安全验证时不会自动打开浏览器，任务会直接提示失败原因。
6. 如果你能在其他环境打开微信文章，可将网页另存为 HTML，或复制完整 HTML 源码，在首页点击**导入网页 HTML**，填写原文链接后导入。

### 微信文章的无浏览器导入

微信验证码页不能通过普通 HTTP、文章令牌或 Agent Reach 直接绕过。当前网站默认不启动浏览器：

- 普通微信链接可直接抓取时，自动保存文章和图片地址。
- 微信返回安全验证页时，任务立即失败，不会保存验证码页，也不会长时间卡住。
- 从已能打开文章的环境保存完整网页 HTML 后，可使用首页的 **导入网页 HTML** 功能；文件需要包含 `#js_content` 正文节点。

### X 长文登录态抓取（可选）

项目支持使用本机 X 登录态读取长文。Cookie 不会保存到网站数据库，后端会调用本机的 `twitter-cli`。

```bash
# 建议在独立虚拟环境中安装 Agent Reach
python3 -m venv ~/.agent-reach-venv
source ~/.agent-reach-venv/bin/activate
pip install https://github.com/Panniantong/agent-reach/archive/main.zip
agent-reach install --env=local --channels=twitter

# 在浏览器登录 X 后，检查当前登录态
twitter status

# 验证长文读取
twitter article "https://x.com/用户名/status/推文ID" --markdown
```

启动 FastAPI 的终端需要能找到 `twitter` 命令。若命令不在 PATH 中，可设置：

```bash
export SYNTHAI_TWITTER_BIN="/path/to/twitter"
```

网站提交 X 长文时，只使用本机 `twitter-cli` 登录态读取全文，不再需要或保存 X Article API Key。模型参数仍可单独保存，但当前不会用于导入任务。

## 技术栈

**Frontend:** React, TypeScript, Vite, Tailwind CSS, Zustand, React Router, Framer Motion
**Backend:** Python, FastAPI, SQLAlchemy, SQLite, OpenAI Python SDK, yt-dlp, trafilatura, BeautifulSoup4
