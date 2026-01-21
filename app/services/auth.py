"""Authentication service for Jellyfin token validation and admin checks."""

import logging
from typing import Optional
from dataclasses import dataclass

from fastapi import Header, HTTPException, Depends, Request, Cookie

from app.clients.jellyfin import jellyfin_client, JellyfinUser
from app.config import settings

logger = logging.getLogger(__name__)

# Cookie name for storing Jellyfin token
AUTH_COOKIE_NAME = "jellyfin_token"


@dataclass
class AuthenticatedUser:
    """Authenticated user from Jellyfin token validation."""
    user_id: str
    username: str
    is_admin: bool


async def get_current_user(
    request: Request,
    x_jellyfin_token: Optional[str] = Header(None, alias="X-Jellyfin-Token"),
    jellyfin_token: Optional[str] = Cookie(None),
) -> Optional[AuthenticatedUser]:
    """
    Dependency to get current user from Jellyfin token.

    Checks for token in this order:
    1. X-Jellyfin-Token header (for API calls)
    2. jellyfin_token cookie (for page loads)

    Returns None if no token provided (anonymous access).
    Raises 401 if token is invalid.

    Usage:
        @app.get("/endpoint")
        async def endpoint(user: Optional[AuthenticatedUser] = Depends(get_current_user)):
            if user:
                print(f"Hello {user.username}")
    """
    # Check header first, then cookie
    token = x_jellyfin_token or jellyfin_token

    if not token:
        return None

    jellyfin_user = await jellyfin_client.validate_token(token)
    if not jellyfin_user:
        # Don't raise 401 for invalid cookies - just treat as anonymous
        # This prevents redirect loops when cookies expire
        if jellyfin_token and not x_jellyfin_token:
            logger.debug("Invalid cookie token, treating as anonymous")
            return None
        raise HTTPException(
            status_code=401,
            detail="Invalid Jellyfin token"
        )

    return AuthenticatedUser(
        user_id=jellyfin_user.user_id,
        username=jellyfin_user.username,
        is_admin=jellyfin_user.is_admin
    )


async def require_authenticated_user(
    user: Optional[AuthenticatedUser] = Depends(get_current_user)
) -> AuthenticatedUser:
    """
    Dependency that requires authentication.

    Raises 401 if not authenticated.

    Usage:
        @app.get("/protected")
        async def protected(user: AuthenticatedUser = Depends(require_authenticated_user)):
            print(f"Hello {user.username}")
    """
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Provide X-Jellyfin-Token header."
        )
    return user


async def require_admin_user(
    user: AuthenticatedUser = Depends(require_authenticated_user)
) -> AuthenticatedUser:
    """
    Dependency that requires admin privileges.

    Raises 401 if not authenticated, 403 if not admin.

    Usage:
        @app.delete("/admin-only")
        async def admin_only(user: AuthenticatedUser = Depends(require_admin_user)):
            print(f"Admin {user.username} is performing action")
    """
    if not user.is_admin:
        logger.warning(f"Non-admin user {user.username} ({user.user_id}) attempted admin action")
        raise HTTPException(
            status_code=403,
            detail="Admin privileges required"
        )
    return user


def is_admin(user_id: str) -> bool:
    """
    Check if a user ID is in the admin list.

    This is a synchronous helper for use in templates/non-async contexts.
    """
    return user_id in settings.admin_user_ids_list


async def get_user_info(user_id: str) -> Optional[JellyfinUser]:
    """
    Get user info by Jellyfin user ID.

    Useful for resolving usernames in audit logs.
    """
    return await jellyfin_client.get_user_by_id(user_id)
