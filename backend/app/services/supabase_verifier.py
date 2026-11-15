"""Cryptographic token verification service for Supabase Auth JWTs.

Validates Supabase-issued user access tokens via:
1. Asymmetric JWKS fetched from Supabase Auth (`/.well-known/jwks.json`).
2. Symmetric JWT secret fallback if configured.
3. Strict standard claim verification: `iss`, `aud`, `exp`, `nbf`, `sub`.
4. Verification of confirmed email and user metadata.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient, PyJWTError

from app.core.config import Settings
from app.core.exceptions import UnauthorizedError
from app.core.logging import log_security_event

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VerifiedSupabaseIdentity:
    """Verified user identity extracted from a cryptographically validated Supabase token."""

    supabase_user_id: str
    email: str
    is_email_verified: bool
    full_name: str | None = None
    raw_claims: dict[str, Any] | None = None


class SupabaseTokenVerifier:
    """Validates Supabase access tokens using asymmetric JWKS or HMAC secret."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._auth_config = settings.supabase_auth
        self._jwks_client: PyJWKClient | None = None

        if self._auth_config.jwks_url:
            self._jwks_client = PyJWKClient(
                self._auth_config.jwks_url,
                cache_keys=True,
                max_cached_keys=16,
            )

    def verify_token(self, token: str) -> VerifiedSupabaseIdentity:
        """Verify the Supabase JWT signature, issuer, audience, and expiration.

        Returns:
            VerifiedSupabaseIdentity with subject, email, verification state, and name.

        Raises:
            UnauthorizedError on any verification failure.
        """
        if not token or not token.strip():
            raise UnauthorizedError(
                "Supabase access token is missing or empty.",
                code="SUPABASE_TOKEN_MISSING",
            )

        token = token.strip()
        expected_audience = self._auth_config.audience
        expected_issuer = self._auth_config.issuer

        # 1. Unverified header inspection for algorithm & kid
        try:
            unverified_header = jwt.get_unverified_header(token)
        except PyJWTError as exc:
            log_security_event(
                event_type="auth.supabase.verify",
                outcome="denied",
                message="Malformed Supabase JWT header.",
                level=logging.WARNING,
            )
            raise UnauthorizedError(
                "Malformed Supabase token.",
                code="SUPABASE_TOKEN_MALFORMED",
            ) from exc

        alg = unverified_header.get("alg", "")
        payload: dict[str, Any]

        # 2. Decode & verify signature
        try:
            if alg in {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}:
                if not self._jwks_client:
                    raise UnauthorizedError(
                        "Supabase JWKS URL not configured for signature verification.",
                        code="SUPABASE_AUTH_NOT_CONFIGURED",
                    )
                signing_key = self._jwks_client.get_signing_key_from_jwt(token)
                key = signing_key.key
                algorithms = [alg]
            elif alg in {"HS256", "HS384", "HS512"}:
                if not self._auth_config.jwt_secret:
                    raise UnauthorizedError(
                        "Supabase JWT secret not configured for symmetric verification.",
                        code="SUPABASE_AUTH_NOT_CONFIGURED",
                    )
                key = self._auth_config.jwt_secret.get_secret_value()
                algorithms = [alg]
            else:
                log_security_event(
                    event_type="auth.supabase.verify",
                    outcome="denied",
                    message=f"Unsupported Supabase JWT algorithm: {alg}",
                    level=logging.WARNING,
                )
                raise UnauthorizedError(
                    f"Unsupported token algorithm '{alg}'.",
                    code="SUPABASE_TOKEN_UNSUPPORTED_ALG",
                )

            decode_kwargs: dict[str, Any] = {
                "algorithms": algorithms,
                "audience": expected_audience,
                "options": {
                    "verify_signature": True,
                    "verify_aud": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "require": ["exp", "sub", "aud"],
                },
            }
            if expected_issuer:
                decode_kwargs["issuer"] = expected_issuer
                decode_kwargs["options"]["verify_iss"] = True
            else:
                decode_kwargs["options"]["verify_iss"] = False

            payload = jwt.decode(token, key=key, **decode_kwargs)

        except jwt.ExpiredSignatureError as exc:
            log_security_event(
                event_type="auth.supabase.verify",
                outcome="denied",
                message="Supabase access token has expired.",
            )
            raise UnauthorizedError(
                "Supabase token has expired.",
                code="SUPABASE_TOKEN_EXPIRED",
            ) from exc
        except jwt.InvalidAudienceError as exc:
            log_security_event(
                event_type="auth.supabase.verify",
                outcome="denied",
                message="Supabase access token audience mismatch.",
                level=logging.WARNING,
            )
            raise UnauthorizedError(
                "Supabase token audience is invalid.",
                code="SUPABASE_TOKEN_AUDIENCE_MISMATCH",
            ) from exc
        except jwt.InvalidIssuerError as exc:
            log_security_event(
                event_type="auth.supabase.verify",
                outcome="denied",
                message="Supabase access token issuer mismatch.",
                level=logging.WARNING,
            )
            raise UnauthorizedError(
                "Supabase token issuer is invalid.",
                code="SUPABASE_TOKEN_ISSUER_MISMATCH",
            ) from exc
        except PyJWTError as exc:
            log_security_event(
                event_type="auth.supabase.verify",
                outcome="denied",
                message=f"Supabase access token verification failed: {exc}",
                level=logging.WARNING,
            )
            raise UnauthorizedError(
                "Supabase token signature verification failed.",
                code="SUPABASE_TOKEN_INVALID",
            ) from exc

        # 3. Extract and validate required subject
        subject = payload.get("sub")
        if not subject or not str(subject).strip():
            log_security_event(
                event_type="auth.supabase.verify",
                outcome="denied",
                message="Supabase token missing subject (sub).",
                level=logging.WARNING,
            )
            raise UnauthorizedError(
                "Supabase token missing valid subject identifier.",
                code="SUPABASE_TOKEN_MISSING_SUBJECT",
            )

        # 4. Extract email and verification status
        raw_email = payload.get("email")
        if not raw_email or not isinstance(raw_email, str) or not raw_email.strip():
            raise UnauthorizedError(
                "Supabase token does not contain an email address.",
                code="SUPABASE_TOKEN_MISSING_EMAIL",
            )

        clean_email = raw_email.strip().lower()

        # In Supabase JWTs, email confirmation is in metadata or confirmed_at
        app_metadata = payload.get("app_metadata") or {}
        user_metadata = payload.get("user_metadata") or {}

        email_confirmed_at = payload.get("email_confirmed_at")
        is_email_verified = bool(
            email_confirmed_at
            or user_metadata.get("email_verified")
            or app_metadata.get("email_verified")
            or payload.get("email_verified")
        )

        full_name = (
            user_metadata.get("full_name")
            or user_metadata.get("name")
            or payload.get("name")
        )

        return VerifiedSupabaseIdentity(
            supabase_user_id=str(subject).strip(),
            email=clean_email,
            is_email_verified=is_email_verified,
            full_name=str(full_name).strip() if full_name else None,
            raw_claims=payload,
        )
