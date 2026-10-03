"""
SynthAI Backend — FastAPI Application Entry Point
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routers import articles, tasks, config, tikhub, models, categories, admin_auth
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

# API 响应 gzip 压缩:文章正文动辄上百 KB,不压缩时公网传输是详情页最大等待来源
app.add_middleware(GZipMiddleware, minimum_size=1024)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件（图片等媒体）——mount 在模块加载时执行，必须先确保目录存在
os.makedirs(settings.MEDIA_DIR, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.MEDIA_DIR), name="media")

# Public local X fonts must also load inside an opaque sandboxed article frame.
@app.middleware("http")
async def public_article_assets(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/media/x/"):
        response.headers["Access-Control-Allow-Origin"] = "*"
    return response


# 路由
app.include_router(articles.router, prefix="/api/v1/articles", tags=["articles"])
app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["tasks"])
app.include_router(config.router, prefix="/api/v1/config", tags=["config"])
app.include_router(tikhub.router, prefix="/api/v1/tikhub", tags=["tikhub"])
app.include_router(categories.router, prefix="/api/v1/categories", tags=["categories"])
app.include_router(admin_auth.router, prefix="/api/v1/admin-auth", tags=["admin-auth"])
app.include_router(models.router, prefix="/api/v1/models", tags=["models"])


@app.get("/")
async def root():
    return {"message": "SynthAI API is running 🚀", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}
