"""文章分类:公开读取(前台菜单/筛选)与整体保存(后台分类管理)。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.routers.admin_auth import require_admin
from app.services.settings_store import load_categories, save_categories

router = APIRouter()


class CategoryListPayload(BaseModel):
    names: list[str] = Field(default_factory=list)


@router.get("")
async def get_categories(db: AsyncSession = Depends(get_db)):
    names = await load_categories()
    return {"names": names}


@router.put("")
async def put_categories(payload: CategoryListPayload, db: AsyncSession = Depends(get_db), _: None = Depends(require_admin)):
    names = await save_categories(payload.names)
    return {"names": names}
