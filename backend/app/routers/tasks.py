import datetime
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy import select

from app.database import get_db
from app.models import Task
from app.services.runtime_store import TASKS_DB
from app.services.task_service import create_task_record, get_task_status, process_task

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
