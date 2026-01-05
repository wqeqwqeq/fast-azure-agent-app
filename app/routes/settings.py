"""Settings API routes."""

from fastapi import APIRouter

from ..dependencies import SettingsDep
from ..schemas import ModelsResponse, SettingsResponse

router = APIRouter()


@router.get("/models", response_model=ModelsResponse)
async def get_models(settings: SettingsDep) -> ModelsResponse:
    """List available LLM models.

    Returns:
        ModelsResponse with list of available model identifiers
    """
    return ModelsResponse(models=settings.available_models)


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(settings: SettingsDep) -> SettingsResponse:
    """Get UI settings/feature flags.

    Returns:
        SettingsResponse with feature flags
    """
    return SettingsResponse(show_func_result=settings.show_func_result)
