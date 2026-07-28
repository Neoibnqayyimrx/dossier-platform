from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.api.routers.auth import router as auth_router
from app.api.routers.ctd import router as ctd_router
from app.api.routers.kb import router as kb_router
from app.api.routers.narrative import router as narrative_router
from app.api.routers.nested import NESTED_ROUTERS
from app.api.routers.products import router as products_router
from app.api.routers.projects import router as projects_router
from app.api.routers.validation import router as validation_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title="Dossier Platform API", version=settings.app_version)

register_error_handlers(app)

app.include_router(auth_router)
app.include_router(products_router)
app.include_router(projects_router)
app.include_router(kb_router)
app.include_router(narrative_router)
app.include_router(validation_router)
app.include_router(ctd_router)
for nested_router in NESTED_ROUTERS:
    app.include_router(nested_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": settings.app_version}
