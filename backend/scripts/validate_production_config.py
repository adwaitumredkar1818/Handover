"""
Production Configuration and Environment Validator.
Enforces that settings adhere to strict production deployment requirements without revealing secrets.
"""

import sys
from typing import List, Tuple
from app.core.config import Settings, get_settings


def validate_production_configuration(settings: Settings) -> Tuple[bool, List[str]]:
    errors: List[str] = []

    # 1. Environment & Mode checks
    if settings.app_env not in ("development", "staging", "production", "test"):
        errors.append(f"Invalid APP_ENV: '{settings.app_env}'")

    # 2. CORS rules
    if settings.app_env == "production":
        if not settings.cors_allowed_origins:
            errors.append("Production requires explicit CORS_ALLOWED_ORIGINS.")
        for origin in settings.cors_allowed_origins:
            if "*" in origin:
                errors.append(f"Wildcard CORS origin '{origin}' is forbidden in production.")
            if "localhost" in origin or "127.0.0.1" in origin:
                errors.append(f"Localhost CORS origin '{origin}' is forbidden in production.")

    # 3. Cookie & SSL security
    if settings.app_env == "production":
        if not settings.cookie_secure:
            errors.append("COOKIE_SECURE must be true in production.")
        if settings.postgres_ssl_mode == "disable":
            errors.append("POSTGRES_SSL_MODE cannot be 'disable' in production.")

    # 4. Critical Cryptographic Keys
    weak_placeholders = {"change-me", "dev-secret", "secret", "insecure", "password", "test", "your-super-secret"}
    for key_name, key_val in [
        ("JWT_SECRET_KEY", settings.jwt_secret_key.get_secret_value() if settings.jwt_secret_key else ""),
        ("TOKEN_ENCRYPTION_KEY", settings.token_encryption_key.get_secret_value() if settings.token_encryption_key else ""),
        ("FILE_ENCRYPTION_KEY", settings.file_encryption_key.get_secret_value() if settings.file_encryption_key else ""),
    ]:
        if not key_val:
            errors.append(f"Missing required key: {key_name}")
        elif settings.app_env == "production" and any(w in key_val.lower() for w in weak_placeholders):
            errors.append(f"Key {key_name} contains an insecure development placeholder.")
        elif len(key_val) < 32:
            errors.append(f"Key {key_name} has insufficient length ({len(key_val)} chars, min 32 required).")

    # 5. Inference Gateway Configuration
    if settings.resolved_inference_mode == "gateway":
        if not settings.inference_gateway.url:
            errors.append("INFERENCE_GATEWAY_URL is required when inference mode is 'gateway'.")
        if not settings.inference_gateway.hmac_secret:
            errors.append("INFERENCE_GATEWAY_HMAC_SECRET is required when inference mode is 'gateway'.")
        elif len(settings.inference_gateway.hmac_secret.get_secret_value()) < 32:
            errors.append("INFERENCE_GATEWAY_HMAC_SECRET must be at least 32 characters.")

    # 6. Database URL protocol and safety
    db_url = settings.database.sqlalchemy_url()
    if not (db_url.startswith("postgresql+psycopg://") or db_url.startswith("postgresql://")):
        errors.append(f"Invalid database dialect in DATABASE_URL: {db_url.split('://')[0]}")

    return (len(errors) == 0, errors)


def main():
    print("======================================================================")
    print("  THE HANDOVER — PRODUCTION CONFIGURATION VALIDATOR")
    print("======================================================================")
    
    settings = get_settings()
    print(f"Current Environment: {settings.app_env}")
    print(f"Inference Mode:      {settings.resolved_inference_mode}")
    print(f"CORS Allowed Origins: {len(settings.cors_allowed_origins)} configured")
    print(f"PostgreSQL SSL Mode: {settings.postgres_ssl_mode}")
    print(f"Cookie Secure:       {settings.cookie_secure}")
    
    is_valid, errors = validate_production_configuration(settings)
    
    if is_valid:
        print("\n[SUCCESS] Production Configuration Validation Passed.")
        sys.exit(0)
    else:
        print(f"\n[ERROR] Found {len(errors)} configuration validation issue(s):")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
