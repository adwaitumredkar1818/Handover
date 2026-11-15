"""Authentication dependencies for the Local Inference Gateway."""

from __future__ import annotations

import hmac
from typing import Annotated
from fastapi import Depends, Header, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from infrastructure.gateway.config import GatewaySettings, get_gateway_settings
from infrastructure.gateway.exceptions import AuthenticationError

_bearer_scheme = HTTPBearer(auto_error=False)


def verify_gateway_api_key(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    settings: Annotated[GatewaySettings, Depends(get_gateway_settings)],
) -> str:
    """Validate Bearer token using constant-time comparison."""
    if not credentials or credentials.scheme.lower() != "bearer":
        raise AuthenticationError(
            message="Authorization credentials missing or invalid scheme. Expected 'Bearer <token>'.",
            error_code="UNAUTHORIZED",
        )

    provided_token = credentials.credentials.strip()
    expected_token = settings.inference_gateway_api_key.get_secret_value().strip()

    if not provided_token or not expected_token:
        raise AuthenticationError(
            message="Gateway authentication secret not configured or token empty.",
            error_code="UNAUTHORIZED",
        )

    # Constant-time comparison prevents timing attacks
    if not hmac.compare_digest(provided_token.encode("utf-8"), expected_token.encode("utf-8")):
        raise AuthenticationError(
            message="Invalid gateway authorization token.",
            error_code="UNAUTHORIZED",
        )

    return provided_token
