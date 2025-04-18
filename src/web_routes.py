from fastapi import APIRouter

from .root_routes import router as root_router
from .project_routes import router as project_router
from .document_routes import router as document_router
from .memory_routes import router as memory_router

router = APIRouter()
router.include_router(root_router)
router.include_router(project_router)
router.include_router(document_router)
router.include_router(memory_router)
