"""The X media mount serves assets, never a parallel article reader."""
from pathlib import Path

from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException


class MediaFiles(StaticFiles):
    async def get_response(self, path, scope):
        if path.startswith('x/') and Path(path).suffix.lower() not in {
            '.jpg', '.jpeg', '.png', '.webp', '.gif', '.mp4', '.webm', '.woff2',
        }:
            raise HTTPException(status_code=404)
        return await super().get_response(path, scope)
