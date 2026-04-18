"""
SynthAI Backend — FastAPI Application Entry Point
"""
import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routers import articles, tasks, config
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化数据库
    await init_db()
    # 确保媒体目录存在
    os.makedirs(settings.MEDIA_DIR, exist_ok=True)
    os.makedirs(settings.ARTICLES_DIR, exist_ok=True)
    yield


app = FastAPI(
    title="SynthAI API",
    description="AI 内容聚合平台后端 API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件（图片等媒体）
app.mount("/media", StaticFiles(directory=settings.MEDIA_DIR), name="media")

# 路由
app.include_router(articles.router, prefix="/api/v1/articles", tags=["articles"])
app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["tasks"])
app.include_router(config.router, prefix="/api/v1/config", tags=["config"])


@app.get("/")
async def root():
    return {"message": "SynthAI API is running 🚀", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}
