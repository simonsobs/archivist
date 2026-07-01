from fastapi import APIRouter

router = APIRouter(prefix="/api/v1")
health_router = APIRouter()

from . import archive, extract, health  # noqa: E402,F401
