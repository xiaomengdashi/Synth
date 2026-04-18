from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import AsyncOpenAI
import json
import os

router = APIRouter()

# 我们将配置保存在 backend 目录下的 config.json 中
CONFIG_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'config.json')

class AppConfigModel(BaseModel):
    apiKey: str
    baseUrl: str
    modelName: str

@router.get("")
async def get_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {"apiKey": "", "baseUrl": "", "modelName": ""}

@router.post("")
async def save_config(config: AppConfigModel):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config.model_dump() if hasattr(config, 'model_dump') else config.dict(), f)
    return {"status": "success"}

class VerifyRequest(BaseModel):
    apiKey: str
    baseUrl: str

@router.post("/verify")
async def verify_and_get_models(data: VerifyRequest):
    try:
        # 创建客户端
        client = AsyncOpenAI(
            api_key=data.apiKey,
            base_url=data.baseUrl,
            timeout=10.0
        )
        # 获取可用模型列表
        models_response = await client.models.list()
        models = [m.id for m in models_response.data]
        
        # 将模型列表进行简单的排序，让常见的大模型排在前面
        models.sort(key=lambda x: ("gpt" not in x.lower(), "claude" not in x.lower(), "qwen" not in x.lower(), x))
        
        return {"status": "success", "models": models}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
