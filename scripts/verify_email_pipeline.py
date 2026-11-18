"""Pipeline verification script for live email verification and auth gate checks."""

from __future__ import annotations

import argparse
import os
import sys
import uuid
import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify email verification pipeline against local backend.")
    parser.add_argument(
        "--email",
        default=os.environ.get("RESEND_TEST_RECIPIENT_EMAIL"),
        help="Email address to verify. In Resend sandbox mode, use account owner email.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("API_BASE_URL", "http://127.0.0.1:8000/api/v1"),
        help="Base backend API URL.",
    )
    args = parser.parse_args()

    email = args.email or f"live_test_{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPassword123!Secure"
    base_url = args.base_url

    print(f"Running email pipeline verification for: {email} against {base_url}")

    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        # Check health
        try:
            health = client.get("/health")
            if health.status_code != 200:
                print(f"[ERROR] Backend at {base_url} returned HTTP {health.status_code}")
                return 1
        except Exception as exc:
            print(f"[ERROR] Cannot connect to backend at {base_url}: {exc}")
            return 1

        # 1. Register
        reg_resp = client.post(
            "/auth/register",
            json={"full_name": "Live Tester", "email": email, "password": password},
        )
        if reg_resp.status_code == 201:
            reg_data = reg_resp.json()
            print("1. Register response delivery status:", reg_data["email_verification_delivery"])
            print("   Register message:", reg_data["message"])
            dev_token = reg_data.get("development_verification_token")
        elif reg_resp.status_code == 409:
            print(f"1. User '{email}' already registered. Continuing with existing account.")
            dev_token = None
        else:
            print(f"1. Register failed (HTTP {reg_resp.status_code}): {reg_resp.text}")
            return 1

        # 2. Login
        login_resp = client.post("/auth/login", json={"email": email, "password": password})
        if login_resp.status_code != 200:
            print(f"2. Login failed (HTTP {login_resp.status_code}): {login_resp.text}")
            return 1
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("2. Login successful, acquired access token.")

        # 3. Authenticated resend with empty body
        resend_resp = client.post("/auth/resend-verification", headers=headers, json={})
        print("3. Authenticated resend status code:", resend_resp.status_code)
        if resend_resp.status_code == 200:
            resend_data = resend_resp.json()
            print("   Delivery status:", resend_data.get("email_verification_delivery"))
            print("   Message:", resend_data.get("message"))

        # 4. Unauthenticated resend without email
        unauth_resp = client.post("/auth/resend-verification", json={})
        assert unauth_resp.status_code == 400
        print("4. Unauthenticated empty resend correctly rejected (HTTP 400):", unauth_resp.json()["error"]["code"])

        # 5. Verify email with token if available
        if dev_token:
            ver_resp = client.post("/auth/verify-email", json={"token": dev_token})
            assert ver_resp.status_code == 200
            print("5. Verified email successfully:", ver_resp.json()["message"])
        else:
            print("5. Skipping token verification (existing verified account).")

        # 6. Read /me
        me_resp = client.get("/auth/me", headers=headers)
        assert me_resp.status_code == 200
        print("6. /auth/me user email verification status:", me_resp.json()["is_email_verified"])

        # 7. Resend after verification
        resend_after = client.post("/auth/resend-verification", headers=headers, json={})
        assert resend_after.status_code == 200
        print("7. Resend after verification message:", resend_after.json()["message"])

    print("\nALL LIVE INTEGRATION CHECKS PASSED SUCCESSFULLY!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

