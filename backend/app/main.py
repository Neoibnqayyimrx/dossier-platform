from fastapi import FastAPI

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title="Dossier Platform API", version=settings.app_version)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": settings.app_version}
