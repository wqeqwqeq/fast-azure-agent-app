"""User API routes."""

from fastapi import APIRouter

from ..dependencies import CurrentUserDep
from ..schemas import UserInfo

router = APIRouter()


@router.get("/user", response_model=UserInfo)
async def get_user(current_user: CurrentUserDep) -> UserInfo:
    """Get current user information from SSO headers or local config.

    Returns:
        UserInfo with user details and authentication status
    """
    return current_user
