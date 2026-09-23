import datetime
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.database import get_db
from app.models import Task
from app.services.runtime_store import TASKS_DB
from app.services.task_service import create_task_record, get_task_status, process_task
from app.services.share_import import extract_shared_url, prepare_shared_task
from app.routers.config import get_config

router = APIRouter()


class ModelConfig(BaseModel):
    modelName: str | None = None
    apiKey: str | None = None
    baseUrl: str | None = None
    biliSessdata: str | None = None
    biliJct: str | None = None
    biliBuvid3: str | None = None


class TaskSubmit(BaseModel):
    url: str
    config: ModelConfig


class ShareSubmit(BaseModel):
    url: str = Field(default="", max_length=16000)
    text: str = Field(default="", max_length=16000)
    title: str = Field(default="", max_length=2000)
    retry: bool = False


@router.post("/share")
async def submit_share(data: ShareSubmit, background_tasks: BackgroundTasks, db=Depends(get_db)):
    try:
        identity, url = extract_shared_url(data.url, data.text, data.title)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result, scheduled = await prepare_shared_task(db, identity, url, data.retry)
    if scheduled:
        task_id = result["task_id"]
        TASKS_DB[task_id] = {**result, "id": task_id}
        config = ModelConfig(**await get_config())
        background_tasks.add_task(process_task, task_id, url, config)
    return result


@router.get("")
async def list_tasks(db=Depends(get_db)):
    result = await db.execute(select(Task).order_by(Task.created_at.desc()).limit(100))
    tasks = result.scalars().all()
    return {"total": len(tasks), "data": jsonable_encoder(tasks)}


@router.post("/submit")
async def submit_task(data: TaskSubmit, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    created_at = datetime.datetime.now().isoformat()

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

    background_tasks.add_task(process_task, task_id, data.url, data.config)
    return {"task_id": task_id, "status": "pending"}


@router.get("/{task_id}/status")
async def get_task_status_route(task_id: str):
    return await get_task_status(task_id)
