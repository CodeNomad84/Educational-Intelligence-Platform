# fastapi_core/auth.py
"""Service-token verification for Django -> FastAPI calls (interim, ADR-0002 PROPOSED).

Django signs a short-lived HS256 JWT (iss ``school-django``, aud ``school-fastapi``) carrying
the end user's id (``sub``) and recognised ``roles``. The shared secret comes ONLY from the
``SERVICE_JWT_SECRET`` environment variable; there is no default. If it is missing or too
short, a known placeholder or low-entropy, every protected route fails closed with 503.
"""
import os
from typing import Callable, Optional

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ISSUER = "school-django"
AUDIENCE = "school-fastapi"
MIN_SECRET_LENGTH = 32

ADMIN = "SchoolAdmin"  # ADR-0010; must equal students/access.py ADMIN in django_core
TEACHER = "Teacher"

# auto_error=False so a missing header is a deterministic 401 (not a version-dependent 403).
security = HTTPBearer(auto_error=False)


_PLACEHOLDER_PREFIXES = ("django-insecure", "changeme", "change-me", "change_me", "your-", "your_",
                         "placeholder", "example", "secret", "password", "replace")
MIN_DISTINCT_CHARS = 10


def _is_weak(secret: str) -> bool:
    """Too short, a known placeholder, or obviously low-entropy (e.g. 'aaaa...')."""
    return (
        len(secret) < MIN_SECRET_LENGTH
        or secret.lower().startswith(_PLACEHOLDER_PREFIXES)
        or len(set(secret)) < MIN_DISTINCT_CHARS
    )


def _secret() -> str:
    secret = os.environ.get("SERVICE_JWT_SECRET", "")
    if _is_weak(secret):
        # Fail closed. Do not say what is wrong beyond "not configured".
        raise HTTPException(status_code=503, detail="Service authentication is not configured.")
    return secret


def validate_service_secret() -> None:
    """Startup check: refuse to run with a missing, weak or placeholder SERVICE_JWT_SECRET.

    The message never contains the value. Request-time checks (503 fail-closed) stay in place.
    """
    if _is_weak(os.environ.get("SERVICE_JWT_SECRET", "")):
        raise RuntimeError(
            "SERVICE_JWT_SECRET is missing, shorter than %d characters, a known placeholder, or "
            "low-entropy. Refusing to start." % MIN_SECRET_LENGTH
        )


def verify_jwt(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """Authenticate the caller. Returns the verified claims."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    secret = _secret()
    try:
        payload = jwt.decode(
            credentials.credentials,
            secret,
            algorithms=["HS256"],
            audience=AUDIENCE,
            issuer=ISSUER,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")
    roles = payload.get("roles")
    if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
        raise HTTPException(status_code=401, detail="Invalid token.")
    return payload


def disabled_in_phase1(payload: dict = Depends(verify_jwt)) -> dict:
    """Dependency for routes switched off in Phase 1 (RAG chat / ingestion / search).

    The caller is still authenticated first (anonymous -> 401); every role, Admin included, gets 403.
    Re-enabling a route means swapping this dependency for ``require_roles(...)`` once the embedding
    model, vector dimension and document-level authorization are verified.
    """
    raise HTTPException(status_code=403, detail="This feature is disabled in Phase 1.")


AI_SCOPE = "ai"      # a token minted by Django for ONE AI call carries scope "ai": valid only on routes that opt in (review F8)


def require_roles(*allowed: str, ai_scope_ok: bool = False) -> Callable[[dict], dict]:
    """Dependency factory: authenticated caller must hold at least one of ``allowed`` roles. A token with ``scope == "ai"`` is refused
    unless the route opts in with ``ai_scope_ok=True`` (only the /llm routes do), so it can never widen access to other routes."""

    def dependency(payload: dict = Depends(verify_jwt)) -> dict:
        if payload.get("scope") == AI_SCOPE and not ai_scope_ok:
            raise HTTPException(status_code=403, detail="Not permitted.")
        if not set(payload["roles"]) & set(allowed):
            raise HTTPException(status_code=403, detail="Not permitted.")
        return payload

    return dependency


def school_ids(payload: dict) -> list:
    """The school ids of the token's ``schools`` claim (SchoolAdmin scope, signed by Django). A missing or malformed claim is an
    invalid token (fail closed: an old token without the claim cannot read or delete any document)."""
    value = payload.get("schools")
    if not isinstance(value, list) or not all(type(v) is int and v > 0 for v in value):
        raise HTTPException(status_code=401, detail="Invalid token.")
    return sorted(set(value))


def require_roles_with_schools(*allowed: str, ai_scope_ok: bool = False) -> Callable[[dict], dict]:
    """Like ``require_roles`` and additionally validates the ``schools`` claim; the payload carries the validated list."""
    base = require_roles(*allowed, ai_scope_ok=ai_scope_ok)

    def dependency(payload: dict = Depends(base)) -> dict:
        return {**payload, "schools": school_ids(payload)}

    return dependency
