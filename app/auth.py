"""
Supabase JWT authentication for the AVRY Careers Service.

Auth is centralized on Supabase across the whole platform. Every service
verifies the Supabase-issued access token using the shared project JWT secret
(SUPABASE_JWT_SECRET). The frontend sends `Authorization: Bearer <token>`.

For backward compatibility during the migration, a legacy backend-issued HS256
token (signed with JWT_SECRET) is also accepted.

Endpoints that expose cross-user (admin) data must depend on `require_admin`.
Public endpoints (vacancy listing, application submission) stay open.
"""

from typing import Optional

from jose import jwt, JWTError
from fastapi import Header, HTTPException, Depends

from app.config import settings

JWT_ALGORITHM = "HS256"

ADMIN_ACCOUNT_TYPES = {"admin", "superadmin"}


def _extract_token(authorization: Optional[str]) -> Optional[str]:
    """Pull the raw token out of an Authorization header value."""
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    # Allow a bare token without the "Bearer" prefix.
    return authorization.strip() or None


def verify_token(token: str) -> Optional[dict]:
    """
    Verify a JWT against the configured secrets (Supabase first, then legacy).

    Returns the decoded payload on success, or None if the token is invalid or
    expired under every configured secret.
    """
    secrets = [s for s in (settings.supabase_jwt_secret, settings.jwt_secret) if s]

    for secret in secrets:
        try:
            return jwt.decode(
                token,
                secret,
                algorithms=[JWT_ALGORITHM],
                options={"verify_aud": False},
            )
        except JWTError:
            continue
    return None


def _account_type(payload: dict) -> Optional[str]:
    """Resolve the account_type claim across Supabase and legacy token shapes."""
    return (
        payload.get("account_type")
        or (payload.get("user_metadata") or {}).get("account_type")
        or (payload.get("app_metadata") or {}).get("account_type")
    )


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """
    FastAPI dependency: extract and verify token from Authorization header.

    Returns the decoded JWT payload on success.
    Raises 401 for missing or invalid/expired tokens.
    """
    token = _extract_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")

    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """
    FastAPI dependency: require an admin/superadmin caller.

    Depends on get_current_user for token verification, then checks the
    account_type claim for admin or superadmin role.
    """
    if _account_type(user) not in ADMIN_ACCOUNT_TYPES:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
