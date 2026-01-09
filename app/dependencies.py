"""FastAPI dependency injection functions."""

import base64
import json
import logging
from typing import Annotated, Any, Dict

from fastapi import Depends, Header, Request

from .config import Settings, get_settings
from .infrastructure import AsyncChatHistoryManager
from .schemas import UserInfo

logger = logging.getLogger(__name__)


async def get_history_manager(request: Request) -> AsyncChatHistoryManager:
    """Get the AsyncChatHistoryManager from app state.

    Args:
        request: FastAPI request object

    Returns:
        AsyncChatHistoryManager instance
    """
    return request.app.state.history_manager


async def get_current_user(
    settings: Annotated[Settings, Depends(get_settings)],
    x_ms_client_principal_id: Annotated[str | None, Header()] = None,
    x_ms_client_principal_name: Annotated[str | None, Header()] = None,
    x_ms_client_principal: Annotated[str | None, Header()] = None,
) -> UserInfo:
    """Extract user information from Azure Easy Auth SSO headers.

    Supports different modes based on CHAT_HISTORY_MODE:
    - local_psql, local_redis: Use test credentials from env
    - postgres, redis: Use real SSO headers from Azure Easy Auth

    Args:
        settings: Application settings
        x_ms_client_principal_id: Azure AD client principal ID header
        x_ms_client_principal_name: Azure AD client principal name header
        x_ms_client_principal: Base64-encoded client principal JSON header

    Returns:
        UserInfo with user details
    """
    mode = settings.chat_history_mode

    # Local testing mode
    if mode in ["local_psql", "local_redis"]:
        return UserInfo(
            user_id=settings.local_test_client_id,
            user_name=settings.local_test_username,
            first_name=settings.local_test_username.split()[0] if settings.local_test_username else "User",
            principal_name=None,
            is_authenticated=True,
            mode=mode,
        )

    # Production mode with SSO headers
    if mode in ["postgres", "redis"]:
        display_name = "Unknown user"
        first_name = "there"

        if x_ms_client_principal:
            try:
                decoded_bytes = base64.b64decode(x_ms_client_principal)
                decoded_principal = json.loads(decoded_bytes.decode("utf-8"))

                # Find 'name' claim in the claims array
                for claim in decoded_principal.get("claims", []):
                    if claim.get("typ") == "name":
                        display_name = claim.get("val", "Unknown user")
                        first_name = display_name.split()[0] if display_name else "there"
                        break
            except Exception:
                pass

        return UserInfo(
            user_id=x_ms_client_principal_id or "unknown",
            user_name=display_name,
            first_name=first_name,
            principal_name=x_ms_client_principal_name,
            is_authenticated=bool(x_ms_client_principal_id and x_ms_client_principal),
            mode=mode,
        )

    # Fallback for local mode (shouldn't be used in this FastAPI version)
    return UserInfo(
        user_id="local_user",
        user_name="Local User",
        first_name="User",
        principal_name=None,
        is_authenticated=False,
        mode="local",
    )


# Type aliases for dependency injection
HistoryManagerDep = Annotated[AsyncChatHistoryManager, Depends(get_history_manager)]
CurrentUserDep = Annotated[UserInfo, Depends(get_current_user)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
