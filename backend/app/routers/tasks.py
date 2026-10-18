import datetime
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from app.timezones import local_iso, jsonable_local as jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.routers.admin_auth import require_admin
from app.database import get_db
from app.models import Task
from app.services.runtime_store import TASKS_DB
from app.services.task_service import create_task_record, get_task_status, process_task
from app.services.share_import import extract_shared_url, prepare_shared_task
from app.routers.config import get_runtime_config

router = APIRouter()


class TaskSubmit(BaseModel):
    url: str


class ShareSubmit(BaseModel):
    url: str = Field(default="", max_length=16000)
    text: str = Field(default="", max_length=16000)
    title: str = Field(default="", max_length=2000)
    retry: bool = False


@router.post("/share")
async def submit_share(data: ShareSubmit, background_tasks: BackgroundTasks, db=Depends(get_db), _: None = Depends(require_admin)):
    # 导入属于管理动作(消耗抓取配额并写库),须持有效令牌;
    # 手机侧在 Safari 登录一次后台即可令 /share 页自动携带
    try:
        identity, url = extract_shared_url(data.url, data.text, data.title)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result, scheduled = await prepare_shared_task(db, identity, url, data.retry)
    if scheduled:
        task_id = result["task_id"]
        TASKS_DB[task_id] = {**result, "id": task_id}
        config = await get_runtime_config()
        background_tasks.add_task(process_task, task_id, url, config)
    return result


@router.get("")
async def list_tasks(db=Depends(get_db), _: None = Depends(require_admin)):
    # 任务列表暴露站长抓取历史,仅后台可见;/{task_id}/status 保持开放供快捷指令轮询
    result = await db.execute(select(Task).order_by(Task.created_at.desc()).limit(100))
    tasks = result.scalars().all()
    return {"total": len(tasks), "data": jsonable_encoder(tasks)}


@router.post("/submit")
async def submit_task(data: TaskSubmit, background_tasks: BackgroundTasks, _: None = Depends(require_admin)):
    # 同 submit_share:导入只对已登录站长开放
    task_id = str(uuid.uuid4())
    created_at = local_iso(datetime.datetime.now(datetime.UTC))

    TASKS_DB[task_id] = {
        "id": task_id,
        "original_url": data.url,
        "status": "pending",
        "current_step": "任务已接收",
        "article_id": None,
        "created_at": created_at,
    }

    try:
        await create_task_record(task_id, data.url, created_at)
    except Exception as exc:
        print(f"Failed to create task in DB: {exc}")

    # 配置（含 TikHub Token）一律由服务端从 SQLite 读取，前端不回传
    config = await get_runtime_config()
    background_tasks.add_task(process_task, task_id, data.url, config)
    return {"task_id": task_id, "status": "pending"}


@router.get("/{task_id}/status")
async def get_task_status_route(task_id: str):
    return await get_task_status(task_id)
