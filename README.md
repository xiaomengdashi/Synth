# SynthAI - 自动化 AI 资讯聚合

SynthAI 是一个全自动的科技与 AI 资讯聚合平台。它可以接收微信公众号、B站、抖音或推特（X）的链接，自动提取音视频和图文内容，并利用大型语言模型（LLM）将其总结、重写为高质量的 Markdown 资讯文章。

## 项目结构

本项目采用前后端分离的架构：

- `frontend/`: 前端应用，基于 React 18 + Vite + TypeScript 构建。
  - 使用 Zustand 进行状态管理。
  - 使用 Tailwind CSS 进行样式开发。
  - 提供可视化的管理控制台，用于提交链接和配置大模型。
- `backend/`: 后端服务，基于 Python FastAPI 构建。
  - 使用 SQLite 存储文章和任务状态。
  - 集成了 `yt-dlp`、`trafilatura` 等抓取工具。
  - 支持通过 OpenAI 兼容 API 调用各种大模型进行内容总结。

## 快速开始

### 1. 启动后端服务

首先，进入 `backend` 目录并配置 Python 环境：

```bash
cd backend

# 创建并激活虚拟环境 (推荐)
python3 -m venv venv
source venv/bin/activate  # Windows 用户使用 venv\Scripts\activate

# 安装依赖
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
3. 点击右上角的**大模型配置**按钮，配置你的 AI 模型 API Key、Base URL 以及模型名称（如 `gpt-4o-mini`）。配置将保存在后端的 `config.json` 中。
4. 在输入框中粘贴支持的链接（微信公众号、B站、推特等），点击**开始处理**。
5. 系统将在后台自动拉取内容并生成文章摘要，你可以在任务列表中监控进度。

## 技术栈

**Frontend:** React, TypeScript, Vite, Tailwind CSS, Zustand, React Router, Framer Motion
**Backend:** Python, FastAPI, SQLAlchemy, SQLite, OpenAI Python SDK, yt-dlp, trafilatura, BeautifulSoup4
