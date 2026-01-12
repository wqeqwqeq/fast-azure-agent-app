"""Settings API routes."""

from fastapi import APIRouter

from ..dependencies import SettingsDep
from ..schemas import SettingsResponse

router = APIRouter()


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(settings: SettingsDep) -> SettingsResponse:
    """Get UI settings/feature flags.

    Returns:
        SettingsResponse with feature flags
    """
    return SettingsResponse(show_func_result=settings.show_func_result)
