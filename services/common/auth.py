"""
Authentication and security dependencies for Salon Payments Ops APIs.
Provides API key validation, Bearer token verification, and correlation ID tracking.
"""

import uuid
from typing import Optional
from fastapi import Header, HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware

from libs.config import settings
from libs.observability.logging import set_correlation_id, get_correlation_id


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Injects and extracts correlation ID for every inbound HTTP request."""

    async def dispatch(self, request: Request, call_next):
        correlation_id = (
            request.headers.get("X-Correlation-ID")
            or request.headers.get("X-Request-ID")
            or str(uuid.uuid4())
        )
        set_correlation_id(correlation_id)

        response: Response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


def verify_payments_auth(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> bool:
    """
    Verifies that incoming payments requests are authorized.
    When `settings.payments_api_key` is configured, rejects unauthenticated callers.
    """
    if not settings.payments_api_key:
        return True  # Dev mode / open endpoint when key is unconfigured

    token = x_api_key
    if not token and authorization:
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        else:
            token = authorization.strip()

    if token != settings.payments_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Payments API Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return True


def verify_approval_auth(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> bool:
    """
    Strict authentication gate for the Approval Service and money-moving executions.
    """
    if not settings.approval_api_key:
        return True  # Open in dev / sandbox when unconfigured

    token = x_api_key
    if not token and authorization:
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        else:
            token = authorization.strip()

    if token != settings.approval_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Valid Ops Manager Approval Key required",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return True
