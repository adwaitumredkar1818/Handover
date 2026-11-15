"""Comprehensive test suite for Backend Inference Gateway Client Integration.

Verifies:
1. Valid gateway bearer token.
2. Missing gateway token.
3. Invalid gateway token.
4. Gateway unavailable.
5. Gateway timeout.
6. Gateway returns HTTP 401.
7. Gateway returns HTTP 403.
8. Gateway returns HTTP 422.
9. Gateway returns HTTP 500.
10. Invalid gateway response schema.
11. Authorized project request.
12. Unauthorized project request.
13. Cross-organization project request.
14. Manipulated project ID.
15. Missing organization/project scope.
16. Tenant filter preservation.
17. No gateway request before backend authorization.
18. No gateway secret exposed in logs.
19. Backend startup with gateway disabled.
20. Backend startup with gateway enabled.
"""

from __future__ import annotations

import logging
import uuid
import pytest
import httpx
from pydantic import SecretStr
from unittest.mock import MagicMock

from app.core.config import InferenceGatewaySettings
from app.core.exceptions import (
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
    UnauthorizedError,
)
from app.services.inference_gateway import (
    InferenceGatewayClient,
    InferenceGatewayClientError,
)
from app.services.rbac import RbacService
from infrastructure.gateway.tests.test_tenant_authorization_chain import create_synthetic_rbac_environment


def make_mock_client(handler) -> InferenceGatewayClient:
    settings = InferenceGatewaySettings(
        enabled=True,
        base_url="http://mock-gateway.local",
        token=SecretStr("mock-test-secret-token-min-32-chars"),
        timeout_seconds=2.0,
    )
    transport = httpx.MockTransport(handler)
    return InferenceGatewayClient(settings=settings, http_transport=transport)


def test_1_valid_gateway_bearer_token():
    """Case 1: Valid gateway bearer token passed in Authorization header."""
    recorded_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal recorded_headers
        recorded_headers = dict(request.headers)
        return httpx.Response(200, json={"status": "ok"})

    client = make_mock_client(handler)
    res = client.check_health()
    assert res == {"status": "ok"}
    assert recorded_headers.get("authorization") == "Bearer mock-test-secret-token-min-32-chars"


def test_2_missing_gateway_token():
    """Case 2: Client initialized without token does not send Authorization header."""
    recorded_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal recorded_headers
        recorded_headers = dict(request.headers)
        return httpx.Response(200, json={"status": "ok"})

    settings = InferenceGatewaySettings(enabled=True, base_url="http://mock-gateway.local", token=None)
    client = InferenceGatewayClient(settings=settings, http_transport=httpx.MockTransport(handler))
    res = client.check_health()
    assert res == {"status": "ok"}
    assert "authorization" not in recorded_headers


def test_3_invalid_gateway_token():
    """Case 3: Invalid gateway token raises UnauthorizedError."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"code": "UNAUTHORIZED", "message": "Invalid gateway token"}})

    client = make_mock_client(handler)
    with pytest.raises(UnauthorizedError) as exc_info:
        client.check_health()
    assert exc_info.value.code == "GATEWAY_UNAUTHORIZED"


def test_4_gateway_unavailable():
    """Case 4: Connection error raises ServiceUnavailableError."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused on 127.0.0.1:8002")

    client = make_mock_client(handler)
    with pytest.raises(ServiceUnavailableError) as exc_info:
        client.check_health()
    assert "Cannot reach Local Inference Gateway" in str(exc_info.value)
    assert exc_info.value.code == "GATEWAY_UNREACHABLE"


def test_5_gateway_timeout():
    """Case 5: Read timeout raises ServiceUnavailableError with GATEWAY_TIMEOUT."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Request timed out")

    client = make_mock_client(handler)
    with pytest.raises(ServiceUnavailableError) as exc_info:
        client.generate_chat(model="qwen3:8b", messages=[{"role": "user", "content": "hi"}])
    assert exc_info.value.code == "GATEWAY_TIMEOUT"


def test_6_gateway_returns_http_401():
    """Case 6: Gateway explicit HTTP 401 returns typed UnauthorizedError."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"code": "UNAUTHORIZED", "message": "Token expired"}})

    client = make_mock_client(handler)
    with pytest.raises(UnauthorizedError) as exc_info:
        client.embed_texts(model="nomic-embed-text", texts=["test"])
    assert exc_info.value.code == "GATEWAY_UNAUTHORIZED"


def test_7_gateway_returns_http_403():
    """Case 7: Gateway returns HTTP 403 raises ForbiddenError."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"code": "FORBIDDEN", "message": "IP restricted"}})

    client = make_mock_client(handler)
    with pytest.raises(ForbiddenError) as exc_info:
        client.check_health()
    assert exc_info.value.code == "GATEWAY_FORBIDDEN"


def test_8_gateway_returns_http_422():
    """Case 8: Gateway returns HTTP 422 validation failure raises InferenceGatewayClientError."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={"error": {"code": "MODEL_NOT_ALLOWED", "message": "Model not permitted."}},
        )

    client = make_mock_client(handler)
    with pytest.raises(InferenceGatewayClientError) as exc_info:
        client.generate_chat(model="unapproved-model", messages=[{"role": "user", "content": "hi"}])
    assert exc_info.value.status_code == 422
    assert "MODEL_NOT_ALLOWED" in exc_info.value.code


def test_9_gateway_returns_http_500():
    """Case 9: Gateway returns HTTP 500 raises ServiceUnavailableError after retries."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"code": "INTERNAL_SERVER_ERROR"}})

    client = make_mock_client(handler)
    with pytest.raises(ServiceUnavailableError) as exc_info:
        client.check_health()
    assert exc_info.value.code == "GATEWAY_SERVICE_UNAVAILABLE"


def test_10_invalid_gateway_response_schema():
    """Case 10: Gateway returns non-JSON raises InferenceGatewayClientError."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<error>Non-JSON response</error>")

    client = make_mock_client(handler)
    with pytest.raises(InferenceGatewayClientError) as exc_info:
        client.check_health()
    assert exc_info.value.code == "GATEWAY_INVALID_RESPONSE"


def test_11_authorized_project_request():
    """Case 11: Authorized project lookup succeeds in resolving context."""
    env = create_synthetic_rbac_environment()
    rbac: RbacService = env["rbac_service"]
    ctx = rbac.resolve_project_context(project_id=env["proj_a1"].id, principal=env["alice_principal"])
    assert ctx.project.id == env["proj_a1"].id
    assert ctx.organisation.id == env["org_a"].id


def test_12_unauthorized_project_request():
    """Case 12: Unauthorized project lookup in same organization raises NotFoundError."""
    env = create_synthetic_rbac_environment()
    rbac: RbacService = env["rbac_service"]
    with pytest.raises(NotFoundError):
        rbac.resolve_project_context(project_id=env["proj_a2"].id, principal=env["alice_principal"])


def test_13_cross_organization_project_request():
    """Case 13: Project in a different organization raises NotFoundError."""
    env = create_synthetic_rbac_environment()
    rbac: RbacService = env["rbac_service"]
    with pytest.raises(NotFoundError):
        rbac.resolve_project_context(project_id=env["proj_b1"].id, principal=env["alice_principal"])


def test_14_manipulated_project_id():
    """Case 14: Random fabricated project UUID raises NotFoundError."""
    env = create_synthetic_rbac_environment()
    rbac: RbacService = env["rbac_service"]
    with pytest.raises(NotFoundError):
        rbac.resolve_project_context(project_id=uuid.uuid4(), principal=env["alice_principal"])


def test_15_missing_organization_or_project_scope():
    """Case 15: Client search_vectors enforces non-empty organisation_id and project_id."""
    def handler(request: httpx.Request) -> httpx.Response:
        import json
        payload = json.loads(request.content.decode())
        if not payload.get("organisation_id") or not payload.get("project_id"):
            return httpx.Response(422, json={"error": {"code": "TENANT_SCOPE_REQUIRED", "message": "Missing scope"}})
        return httpx.Response(200, json={"hits": []})

    client = make_mock_client(handler)
    with pytest.raises(InferenceGatewayClientError) as exc_info:
        client.search_vectors(collection_name="test", organisation_id="", project_id="proj-1")
    assert exc_info.value.status_code == 422


def test_16_tenant_filter_preservation():
    """Case 16: Gateway vector search preserves tenant boundaries and custom where filters."""
    recorded_payload = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal recorded_payload
        import json
        recorded_payload = json.loads(request.content.decode())
        return httpx.Response(200, json={"collection_name": "test", "total_hits": 1, "hits": [], "duration_ms": 10.0})

    client = make_mock_client(handler)
    client.search_vectors(
        collection_name="ipkrh_evidence_chunks_nomic-embed-text_v1",
        organisation_id="org-123",
        project_id="proj-456",
        query_embedding=[0.1] * 768,
        where={"category": {"$eq": "decision"}},
    )
    assert recorded_payload["organisation_id"] == "org-123"
    assert recorded_payload["project_id"] == "proj-456"
    assert recorded_payload["where"] == {"category": {"$eq": "decision"}}


def test_17_no_gateway_request_before_backend_authorization():
    """Case 17: Backend authorization failure completely prevents gateway request."""
    gateway_invoked = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal gateway_invoked
        gateway_invoked = True
        return httpx.Response(200, json={"status": "ok"})

    env = create_synthetic_rbac_environment()
    rbac: RbacService = env["rbac_service"]

    # Alice attempts access to Bob's Project B1
    try:
        ctx = rbac.resolve_project_context(project_id=env["proj_b1"].id, principal=env["alice_principal"])
        # Should not reach here
        client = make_mock_client(handler)
        client.search_vectors(collection_name="test", organisation_id=str(ctx.organisation.id), project_id=str(ctx.project.id))
    except NotFoundError:
        pass

    assert not gateway_invoked, "Gateway was invoked despite authorization failure!"


def test_18_no_gateway_secret_exposed_in_logs(caplog):
    """Case 18: Gateway bearer tokens and secrets are never logged."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"})

    token_str = "sensitive-super-secret-token-value-xyz"
    settings = InferenceGatewaySettings(
        enabled=True,
        base_url="http://mock-gateway.local",
        token=SecretStr(token_str),
    )
    client = InferenceGatewayClient(settings=settings, http_transport=httpx.MockTransport(handler))

    with caplog.at_level(logging.DEBUG):
        client.check_health()

    assert token_str not in caplog.text


def test_19_backend_startup_with_gateway_disabled():
    """Case 19: Dependency resolver returns None when gateway is disabled."""
    from app.api.deps import get_inference_gateway_client

    request = MagicMock()
    request.app.state.inference_gateway_client = None

    settings_disabled = MagicMock()
    settings_disabled.gateway.enabled = False

    client = get_inference_gateway_client(request=request, settings=settings_disabled)
    assert client is None


def test_20_backend_startup_with_gateway_enabled():
    """Case 20: Dependency resolver constructs InferenceGatewayClient when enabled."""
    from app.api.deps import get_inference_gateway_client

    request = MagicMock()
    request.app.state.inference_gateway_client = None
    request.app.state.gateway_http_transport = None

    settings_enabled = MagicMock()
    settings_enabled.gateway.enabled = True
    settings_enabled.gateway.base_url = "http://127.0.0.1:8002"
    settings_enabled.gateway.token = SecretStr("token")
    settings_enabled.gateway.timeout_seconds = 30.0
    settings_enabled.gateway.cf_access_client_id = None
    settings_enabled.gateway.cf_access_client_secret = None

    client = get_inference_gateway_client(request=request, settings=settings_enabled)
    assert client is not None
    assert isinstance(client, InferenceGatewayClient)


# ==============================================================================
# SEC-01: CLOUDFLARE ACCESS DESTINATION PROTECTION TESTS
# ==============================================================================

def test_sec01_valid_approved_https_destination():
    """SEC-01: Valid approved HTTPS destination correctly attaches Cloudflare Access headers."""
    recorded_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal recorded_headers
        recorded_headers = dict(request.headers)
        return httpx.Response(200, json={"status": "ok"})

    settings = InferenceGatewaySettings(
        enabled=True,
        base_url="https://gateway-ai.testdomain.com",
        token=SecretStr("mock-token-min-32-chars-xxxxxxxxx"),
        cf_access_client_id="cf-client-id-12345",
        cf_access_client_secret=SecretStr("cf-client-secret-67890"),
        cf_access_allowed_host="gateway-ai.testdomain.com",
    )
    client = InferenceGatewayClient(settings=settings, http_transport=httpx.MockTransport(handler))
    res = client.check_health()
    assert res == {"status": "ok"}
    assert recorded_headers.get("cf-access-client-id") == "cf-client-id-12345"
    assert recorded_headers.get("cf-access-client-secret") == "cf-client-secret-67890"
    assert recorded_headers.get("authorization") == "Bearer mock-token-min-32-chars-xxxxxxxxx"


def test_sec01_missing_approved_hostname():
    """SEC-01: Reject Cloudflare credentials if CF_ACCESS_ALLOWED_HOST is not provided."""
    with pytest.raises(ValueError, match="CF_ACCESS_ALLOWED_HOST must be explicitly configured"):
        InferenceGatewaySettings(
            enabled=True,
            base_url="https://gateway-ai.testdomain.com",
            cf_access_client_id="cf-client-id-12345",
            cf_access_client_secret=SecretStr("cf-client-secret-67890"),
            cf_access_allowed_host=None,
        )


def test_sec01_hostname_mismatch():
    """SEC-01: Reject if base_url hostname does not match CF_ACCESS_ALLOWED_HOST."""
    with pytest.raises(ValueError, match="does not match approved CF_ACCESS_ALLOWED_HOST"):
        InferenceGatewaySettings(
            enabled=True,
            base_url="https://unauthorized-domain.com",
            cf_access_client_id="cf-client-id-12345",
            cf_access_client_secret=SecretStr("cf-client-secret-67890"),
            cf_access_allowed_host="gateway-ai.testdomain.com",
        )


def test_sec01_http_destination_with_cloudflare_credentials():
    """SEC-01: Reject plaintext HTTP URL when Cloudflare credentials are provided."""
    with pytest.raises(ValueError, match="must use HTTPS scheme"):
        InferenceGatewaySettings(
            enabled=True,
            base_url="http://gateway-ai.testdomain.com",
            cf_access_client_id="cf-client-id-12345",
            cf_access_client_secret=SecretStr("cf-client-secret-67890"),
            cf_access_allowed_host="gateway-ai.testdomain.com",
        )


def test_sec01_localhost_destination():
    """SEC-01: Reject localhost destination when Cloudflare credentials are provided."""
    with pytest.raises(ValueError, match="cannot be attached to localhost or loopback"):
        InferenceGatewaySettings(
            enabled=True,
            base_url="https://localhost:8002",
            cf_access_client_id="cf-client-id-12345",
            cf_access_client_secret=SecretStr("cf-client-secret-67890"),
            cf_access_allowed_host="localhost",
        )


def test_sec01_127_0_0_1_destination():
    """SEC-01: Reject 127.0.0.1 loopback destination when Cloudflare credentials are provided."""
    with pytest.raises(ValueError, match="cannot be attached to localhost or loopback"):
        InferenceGatewaySettings(
            enabled=True,
            base_url="https://127.0.0.1:8002",
            cf_access_client_id="cf-client-id-12345",
            cf_access_client_secret=SecretStr("cf-client-secret-67890"),
            cf_access_allowed_host="127.0.0.1",
        )


def test_sec01_private_ip_destination():
    """SEC-01: Reject private RFC1918 IP address when Cloudflare credentials are provided."""
    with pytest.raises(ValueError, match="cannot be attached to IP address"):
        InferenceGatewaySettings(
            enabled=True,
            base_url="https://192.168.1.100:8002",
            cf_access_client_id="cf-client-id-12345",
            cf_access_client_secret=SecretStr("cf-client-secret-67890"),
            cf_access_allowed_host="192.168.1.100",
        )


def test_sec01_link_local_ip_destination():
    """SEC-01: Reject link-local IP (169.254.x.x) destination."""
    with pytest.raises(ValueError, match="cannot be attached to IP address"):
        InferenceGatewaySettings(
            enabled=True,
            base_url="https://169.254.169.254",
            cf_access_client_id="cf-client-id-12345",
            cf_access_client_secret=SecretStr("cf-client-secret-67890"),
            cf_access_allowed_host="169.254.169.254",
        )


def test_sec01_url_with_embedded_credentials():
    """SEC-01: Reject URLs containing embedded credentials."""
    with pytest.raises(ValueError, match="must not contain embedded user credentials"):
        InferenceGatewaySettings(
            enabled=True,
            base_url="https://user:pass@gateway-ai.testdomain.com",
            cf_access_client_id="cf-client-id-12345",
            cf_access_client_secret=SecretStr("cf-client-secret-67890"),
            cf_access_allowed_host="gateway-ai.testdomain.com",
        )


def test_sec01_redirect_blocked():
    """SEC-01: Automatic redirect following is disabled; returns GATEWAY_REDIRECT_BLOCKED."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://malicious-redirect.com"})

    client = make_mock_client(handler)
    with pytest.raises(InferenceGatewayClientError) as exc_info:
        client.check_health()
    assert exc_info.value.code == "GATEWAY_REDIRECT_BLOCKED"
    assert exc_info.value.status_code == 302


def test_sec01_local_mode_without_cloudflare_credentials():
    """SEC-01: Local mode (http://127.0.0.1:8002) works cleanly without Cloudflare credentials."""
    recorded_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal recorded_headers
        recorded_headers = dict(request.headers)
        return httpx.Response(200, json={"status": "ok"})

    settings = InferenceGatewaySettings(
        enabled=True,
        base_url="http://127.0.0.1:8002",
        token=SecretStr("local-bearer-token"),
        cf_access_client_id=None,
        cf_access_client_secret=None,
        cf_access_allowed_host=None,
    )
    client = InferenceGatewayClient(settings=settings, http_transport=httpx.MockTransport(handler))
    res = client.check_health()
    assert res == {"status": "ok"}
    assert "cf-access-client-id" not in recorded_headers
    assert "cf-access-client-secret" not in recorded_headers
    assert recorded_headers.get("authorization") == "Bearer local-bearer-token"


# ==============================================================================
# SEC-02: RETRY SAFETY AND IDEMPOTENCY TESTS
# ==============================================================================

def test_sec02_chat_http_500_exactly_one_request():
    """SEC-02: Non-idempotent chat POST on HTTP 500 is executed exactly once (no retry)."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(500, json={"error": "internal_error"})

    client = make_mock_client(handler)
    with pytest.raises(ServiceUnavailableError):
        client.generate_chat(model="qwen3:8b", messages=[{"role": "user", "content": "hi"}])
    assert call_count == 1, f"Expected exactly 1 call for chat, but got {call_count}"


def test_sec02_chat_http_502_exactly_one_request():
    """SEC-02: Non-idempotent chat POST on HTTP 502 is executed exactly once (no retry)."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(502, json={"error": "bad_gateway"})

    client = make_mock_client(handler)
    with pytest.raises(ServiceUnavailableError):
        client.generate_chat(model="qwen3:8b", messages=[{"role": "user", "content": "hi"}])
    assert call_count == 1, f"Expected exactly 1 call for chat, but got {call_count}"


def test_sec02_chat_connect_error_no_retry():
    """SEC-02: Non-idempotent chat POST on connection error fails immediately (no retry)."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectError("Connection refused")

    client = make_mock_client(handler)
    with pytest.raises(ServiceUnavailableError):
        client.generate_chat(model="qwen3:8b", messages=[{"role": "user", "content": "hi"}])
    assert call_count == 1, f"Expected exactly 1 call for chat, but got {call_count}"


def test_sec02_embedding_retry_behavior():
    """SEC-02: Embedding POST is idempotent and retries once on transient HTTP 503."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(503, json={"error": "temporarily_unavailable"})
        return httpx.Response(200, json={"embeddings": [[0.1] * 768]})

    client = make_mock_client(handler)
    res = client.embed_texts(model="nomic-embed-text", texts=["test"])
    assert len(res) == 1
    assert call_count == 2, f"Expected 2 calls for retryable embedding, got {call_count}"


def test_sec02_vector_search_retry_behavior():
    """SEC-02: Vector search POST is read-only and retries once on transient HTTP 502."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(502, json={"error": "bad_gateway"})
        return httpx.Response(200, json={"collection_name": "test", "total_hits": 0, "hits": [], "duration_ms": 5.0})

    client = make_mock_client(handler)
    res = client.search_vectors(
        collection_name="test_col",
        organisation_id="org-1",
        project_id="proj-1",
        query_embedding=[0.1] * 768,
    )
    assert res["total_hits"] == 0
    assert call_count == 2, f"Expected 2 calls for retryable vector search, got {call_count}"


# ==============================================================================
# SEC-03: AGGREGATE REQUEST DEADLINE TESTS
# ==============================================================================

def test_sec03_deadline_expires_before_retry():
    """SEC-03: If remaining time budget is zero, retry is aborted and GATEWAY_TIMEOUT raised."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        import time
        time.sleep(0.3)  # Consume the entire 0.2s budget on attempt 1
        return httpx.Response(503, json={"error": "unavailable"})

    settings = InferenceGatewaySettings(
        enabled=True,
        base_url="http://mock-gateway.local",
        token=SecretStr("mock-token"),
        timeout_seconds=0.2,
    )
    client = InferenceGatewayClient(settings=settings, http_transport=httpx.MockTransport(handler))
    with pytest.raises(ServiceUnavailableError) as exc_info:
        client.embed_texts(model="nomic-embed-text", texts=["hello"])
    assert exc_info.value.code == "GATEWAY_TIMEOUT"
    assert call_count == 1, f"Expected attempt 2 to be blocked by deadline, but got {call_count} calls"


def test_sec03_deadline_expires_during_backoff():
    """SEC-03: If remaining budget is less than retry backoff (0.5s), abort immediately."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(503, json={"error": "unavailable"})

    # Budget 0.3s is less than attempt 1 backoff (0.5s)
    settings = InferenceGatewaySettings(
        enabled=True,
        base_url="http://mock-gateway.local",
        token=SecretStr("mock-token"),
        timeout_seconds=0.3,
    )
    client = InferenceGatewayClient(settings=settings, http_transport=httpx.MockTransport(handler))
    with pytest.raises(ServiceUnavailableError) as exc_info:
        client.embed_texts(model="nomic-embed-text", texts=["hello"])
    assert exc_info.value.code == "GATEWAY_TIMEOUT"
    assert "deadline expired before retry backoff" in str(exc_info.value)
    assert call_count == 1


# ==============================================================================
# SEC-04: HTTP CLIENT LIFECYCLE REUSE TESTS
# ==============================================================================

def test_sec04_client_lifecycle_reuse():
    """SEC-04: Client correctly reuses provided httpx.Client across multiple requests."""
    shared_client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"status": "ok"})),
        follow_redirects=False,
    )
    settings = InferenceGatewaySettings(enabled=True, base_url="http://mock-gateway.local", token=SecretStr("tok"))
    client = InferenceGatewayClient(settings=settings, http_client=shared_client)

    res1 = client.check_health()
    res2 = client.check_health()
    assert res1 == {"status": "ok"}
    assert res2 == {"status": "ok"}
    assert not shared_client.is_closed
    shared_client.close()
    assert shared_client.is_closed
