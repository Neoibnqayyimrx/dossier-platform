from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_error_handlers
from app.api.routers.admin import router as admin_router
from app.api.routers.applicability import router as applicability_router
from app.api.routers.applicants import router as applicants_router
from app.api.routers.artifacts import router as artifacts_router
from app.api.routers.auth import router as auth_router
from app.api.routers.ctd import router as ctd_router
from app.api.routers.documents import router as documents_router
from app.api.routers.ectd import router as ectd_router
from app.api.routers.enums import router as enums_router
from app.api.routers.kb import router as kb_router
from app.api.routers.narrative import router as narrative_router
from app.api.routers.batch_results import router as batch_results_router
from app.api.routers.bioequivalence_results import router as bioequivalence_results_router
from app.api.routers.stability_results import router as stability_results_router
from app.api.routers.nested import NESTED_ROUTERS
from app.api.routers.product_information import router as product_information_router
from app.api.routers.products import router as products_router
from app.api.routers.projects import router as projects_router
from app.api.routers.regions import router as regions_router
from app.api.routers.sections import router as sections_router
from app.api.routers.superadmin import router as superadmin_router
from app.api.routers.validation import router as validation_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title="Dossier Platform API", version=settings.app_version)

# P11: the frontend runs on its own origin, so browsers preflight every
# request here. Without this the entire API is unreachable from a browser
# -- something no backend test caught, because httpx (unlike a browser)
# doesn't enforce the same-origin policy. Origins come from config, never
# a "*" wildcard (see Settings.cors_allow_origins for why).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # gap Phase 5b: a cross-origin script may read only CORS-safelisted
    # response headers unless the server exposes others. Content-Disposition
    # is not safelisted, so without this the UI could not read the filename
    # the report endpoint chose -- and would save every report under one
    # generic name. Another thing httpx-based tests cannot see.
    expose_headers=["Content-Disposition"],
)

register_error_handlers(app)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(superadmin_router)
app.include_router(applicants_router)
app.include_router(products_router)
app.include_router(product_information_router)
app.include_router(projects_router)
app.include_router(applicability_router)
app.include_router(kb_router)
app.include_router(narrative_router)
app.include_router(validation_router)
app.include_router(ctd_router)
app.include_router(ectd_router)
app.include_router(enums_router)
app.include_router(regions_router)
app.include_router(sections_router)
app.include_router(documents_router)
app.include_router(artifacts_router)
app.include_router(batch_results_router)
app.include_router(stability_results_router)
app.include_router(bioequivalence_results_router)
for nested_router in NESTED_ROUTERS:
    app.include_router(nested_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": settings.app_version}
