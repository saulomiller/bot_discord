"""agrega e registra todos os routers de endpoints da API."""

from fastapi import APIRouter

from api.endpoints.playback import router as playback_router
from api.endpoints.playlists import router as playlists_router
from api.endpoints.radios import router as radios_router
from api.endpoints.security import router as security_router
from api.endpoints.settings import router as settings_router
from api.endpoints.soundboard import router as soundboard_router
from api.endpoints.status import router as status_router

router = APIRouter()

router.include_router(security_router)
router.include_router(status_router)
router.include_router(playback_router)
router.include_router(settings_router)
router.include_router(playlists_router)
router.include_router(soundboard_router)
router.include_router(radios_router)
