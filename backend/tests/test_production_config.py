import pytest
from pydantic_core import ValidationError
from app.core.config import Settings
from backend.scripts.validate_production_config import validate_production_configuration

def test_production_config_rejects_insecure_cookies_at_instantiation():
    # Settings model-level validator already rejects COOKIE_SECURE=False in production!
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            cors_allowed_origins=["https://thehandover.app"],
            cookie_secure=False,
            postgres_ssl_mode="require",
            jwt_secret_key="a"*32,
            token_encryption_key="b"*32,
            file_encryption_key="c"*32,
            postgres_password="d"*16,
        )
    assert "COOKIE_SECURE must be true in production" in str(exc_info.value)

def test_production_config_rejects_wildcard_cors():
    # Settings model-level validator already rejects '*' in cors_allowed_origins
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            cors_allowed_origins=["*"],
            cookie_secure=True,
            postgres_ssl_mode="require",
            jwt_secret_key="a"*32,
            token_encryption_key="b"*32,
            file_encryption_key="c"*32,
            postgres_password="d"*16,
        )
    assert "Wildcard '*' is not allowed" in str(exc_info.value)

def test_production_config_passes_valid_prod_settings():
    settings = Settings(
        app_env="production",
        cors_allowed_origins=["https://thehandover.app"],
        cookie_secure=True,
        postgres_ssl_mode="require",
        jwt_secret_key="a"*32,
        token_encryption_key="b"*32,
        file_encryption_key="c"*32,
        postgres_password="d"*16,
    )
    is_valid, errors = validate_production_configuration(settings)
    assert is_valid
    assert len(errors) == 0
