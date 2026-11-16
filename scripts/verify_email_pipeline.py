import uuid
import httpx

base_url = "http://127.0.0.1:8000/api/v1"
email = f"live_test_{uuid.uuid4().hex[:8]}@example.com"
password = "TestPassword123!Secure"

with httpx.Client(base_url=base_url, timeout=30.0) as client:
    # 1. Register
    reg_resp = client.post(
        "/auth/register",
        json={"full_name": "Live Tester", "email": email, "password": password},
    )
    assert reg_resp.status_code == 201, f"Register failed: {reg_resp.text}"
    reg_data = reg_resp.json()
    print("1. Register response delivery status:", reg_data["email_verification_delivery"])
    print("   Register message:", reg_data["message"])
    dev_token = reg_data["development_verification_token"]
    assert dev_token is not None, "Expected development verification token in dev mode"

    # 2. Login while unverified
    login_resp = client.post("/auth/login", json={"email": email, "password": password})
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Authenticated resend with empty body
    resend_resp = client.post("/auth/resend-verification", headers=headers, json={})
    assert resend_resp.status_code == 200, f"Resend failed: {resend_resp.text}"
    resend_data = resend_resp.json()
    print("2. Authenticated resend delivery status:", resend_data["email_verification_delivery"])
    print("   Resend message:", resend_data["message"])

    # 4. Unauthenticated resend without email
    unauth_resp = client.post("/auth/resend-verification", json={})
    assert unauth_resp.status_code == 400
    print("3. Unauthenticated empty resend correctly rejected (HTTP 400):", unauth_resp.json()["error"]["code"])

    # 5. Verify email with token
    ver_resp = client.post("/auth/verify-email", json={"token": dev_token})
    assert ver_resp.status_code == 200
    print("4. Verified email successfully:", ver_resp.json()["message"])

    # 6. Read /me
    me_resp = client.get("/auth/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["is_email_verified"] is True
    print("5. /auth/me confirms user is verified:", me_resp.json()["is_email_verified"])

    # 7. Resend after verification
    resend_after = client.post("/auth/resend-verification", headers=headers, json={})
    assert resend_after.status_code == 200
    print("6. Resend after verification:", resend_after.json()["message"])

print("\nALL LIVE INTEGRATION CHECKS PASSED SUCCESSFULLY!")
