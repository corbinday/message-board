"""
FastAPI dependencies for authentication and database client injection.

This module replaces Flask's `g` object and Flask-Login with dependency injection.
The key pattern is:
- `get_current_user`: Extracts user from cookie (optional, returns None if not authenticated)
- `require_user`: Requires authentication (raises 401 if not authenticated)
- `get_client`: Provides a scoped Gel client with user context injected
"""

from typing import Optional, Annotated
from fastapi import Request, Depends, HTTPException, Cookie
from fastapi.responses import RedirectResponse
import gel


class User:
    """Simple user class representing an authenticated user."""

    def __init__(self, auth_token: str):
        self.id = auth_token
        self.is_authenticated = True


# Type alias for optional user
OptionalUser = Optional[User]


async def get_current_user(
    gel_auth_token: Annotated[Optional[str], Cookie(alias="gel-auth-token")] = None,
) -> OptionalUser:
    """
    Extract the current user from the auth cookie.
    Returns None if not authenticated (doesn't raise an error).
    """
    if gel_auth_token:
        return User(gel_auth_token)
    return None


async def require_user(
    user: OptionalUser = Depends(get_current_user),
) -> User:
    """
    Require an authenticated user.
    Raises 401 if not authenticated.
    """
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


async def get_base_client(request: Request) -> gel.AsyncIOClient:
    """Get the base Gel client from app state."""
    return request.app.state.get_base_client()


async def get_client(
    request: Request,
    user: OptionalUser = Depends(get_current_user),
) -> gel.AsyncIOClient:
    """
    Provide a scoped Gel client with user context.

    This replaces the Flask pattern of:
        @app.before_request
        def initialize_gel_client():
            if current_user.is_authenticated:
                g.client = base_client.with_globals(...)
            else:
                g.client = base_client

    In FastAPI, we use dependency injection instead. Each request gets
    a client with the appropriate globals set.
    """
    base_client = request.app.state.get_base_client()

    if user:
        # Return client with user's auth token in globals
        return base_client.with_globals({"ext::auth::client_token": user.id})
    else:
        # Return base client for unauthenticated requests
        return base_client


async def get_authenticated_client(
    request: Request,
    user: User = Depends(require_user),
) -> gel.AsyncIOClient:
    """
    Provide a scoped Gel client that requires authentication.
    Combines require_user and get_client for protected routes.
    """
    base_client = request.app.state.get_base_client()
    return base_client.with_globals({"ext::auth::client_token": user.id})


# Annotated types for cleaner dependency injection in routes
CurrentUser = Annotated[OptionalUser, Depends(get_current_user)]
RequiredUser = Annotated[User, Depends(require_user)]
Client = Annotated[gel.AsyncIOClient, Depends(get_client)]
AuthenticatedClient = Annotated[gel.AsyncIOClient, Depends(get_authenticated_client)]
