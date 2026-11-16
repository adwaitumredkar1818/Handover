#!/usr/bin/env python3
"""Automated live transactional email verification tooling for Resend.

Tests live email delivery against the Resend API (direct provider mode)
and against local backend endpoints (API mode).

Usage examples:
    # Direct provider test to account owner email (no backend server required):
    python scripts/verify_live_resend_email.py --email user@example.com --direct

    # Run all live API flows against running backend:
    python scripts/verify_live_resend_email.py --email user@example.com --base-url http://127.0.0.1:8000/api/v1 --flow all

    # Run specific flow:
    python scripts/verify_live_resend_email.py --email user@example.com --flow password-reset
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
import uuid

# Ensure backend package is in python path
repo_root = pathlib.Path(__file__).resolve().parent.parent
backend_dir = repo_root / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import httpx
from app.core.config import Settings
from app.services.email import (
    EmailDeliveryResult,
    EmailMessage,
    ResendEmailProvider,
    TransactionalEmailService,
)


def _print_banner(title: str) -> None:
    width = 70
    print("\n" + "=" * width)
    print(f"  {title.upper()}")
    print("=" * width)


def _print_step(num: int, title: str) -> None:
    print(f"\n[{num}] {title}")
    print("-" * 50)


def _check_sandbox_warning(result: EmailDeliveryResult) -> None:
    if result.status == "failed" and result.error_message:
        if "sandbox" in result.error_message.lower() or "testing domain" in result.error_message.lower():
            print("\n  [!] RESEND SANDBOX RESTRICTION DETECTED:")
            print(f"      {result.error_message}")
            print("      Note: In free sandbox mode, 'onboarding@resend.dev' can only send")
            print("      emails to the email address registered as your Resend account owner.")
            print("      To send to any recipient, verify a custom domain at https://resend.com/domains.\n")


def run_direct_verification(email: str, settings: Settings) -> bool:
    """Directly test TransactionalEmailService and ResendEmailProvider with live credentials."""
    _print_banner("Direct Resend Provider Verification")
    print(f"Recipient Email  : {email}")
    print(f"Email Provider   : {settings.email.provider}")
    print(f"From Address     : {settings.email.from_address}")
    print(f"Delivery Enabled : {settings.email.delivery_enabled}")
    print(f"Frontend URL     : {settings.email.frontend_base_url}")

    if not settings.email.resend_api_key or not settings.email.resend_api_key.get_secret_value():
        print("\n[ERROR] RESEND_API_KEY is not configured in backend environment (.env).")
        print("Please configure RESEND_API_KEY to test live Resend delivery.")
        return False

    api_key = settings.email.resend_api_key.get_secret_value()
    provider = ResendEmailProvider(
        api_key=api_key,
        from_address=settings.email.from_address,
        from_name=settings.email.from_name,
        timeout_seconds=settings.email.http_timeout_seconds,
    )
    email_service = TransactionalEmailService(settings=settings, provider=provider)

    success_count = 0
    total_steps = 3

    # Step 1: Verification Email
    _print_step(1, "Direct Dispatch: Account Email Verification")
    test_ver_token = f"direct_ver_{uuid.uuid4().hex[:16]}"
    ver_res = email_service.send_verification_email(
        to_email=email,
        recipient_name="Direct Verification Tester",
        raw_token=test_ver_token,
    )
    print(f"  Status        : {ver_res.status}")
    print(f"  Provider      : {ver_res.provider}")
    print(f"  Message ID    : {ver_res.provider_message_id or 'None'}")
    if ver_res.error_message:
        print(f"  Error Detail  : {ver_res.error_message}")
        _check_sandbox_warning(ver_res)
    if ver_res.status == "submitted":
        success_count += 1
        print("  --> Verification email submitted successfully!")

    # Step 2: Password Reset Email
    _print_step(2, "Direct Dispatch: Password Reset")
    test_reset_token = f"direct_reset_{uuid.uuid4().hex[:16]}"
    reset_res = email_service.send_password_reset_email(
        to_email=email,
        recipient_name="Direct Password Tester",
        raw_token=test_reset_token,
        expires_in_minutes=30,
    )
    print(f"  Status        : {reset_res.status}")
    print(f"  Provider      : {reset_res.provider}")
    print(f"  Message ID    : {reset_res.provider_message_id or 'None'}")
    if reset_res.error_message:
        print(f"  Error Detail  : {reset_res.error_message}")
        _check_sandbox_warning(reset_res)
    if reset_res.status == "submitted":
        success_count += 1
        print("  --> Password reset email submitted successfully!")

    # Step 3: Project Invitation Email
    _print_step(3, "Direct Dispatch: Project Workspace Invitation")
    test_inv_token = f"direct_inv_{uuid.uuid4().hex[:16]}"
    inv_res = email_service.send_project_invitation_email(
        to_email=email,
        raw_token=test_inv_token,
        organisation_name="Acme Handover Systems",
        project_name="Core Knowledge Reconstruction",
        project_role_name="project_member",
        inviter_name="Lead Engineer",
        expires_in_hours=72,
    )
    print(f"  Status        : {inv_res.status}")
    print(f"  Provider      : {inv_res.provider}")
    print(f"  Message ID    : {inv_res.provider_message_id or 'None'}")
    if inv_res.error_message:
        print(f"  Error Detail  : {inv_res.error_message}")
        _check_sandbox_warning(inv_res)
    if inv_res.status == "submitted":
        success_count += 1
        print("  --> Project invitation email submitted successfully!")

    _print_banner(f"Direct Verification Results: {success_count}/{total_steps} Passed")
    return success_count == total_steps


def run_api_verification(base_url: str, email: str, flows: list[str]) -> bool:
    """Test live email flows against running backend HTTP endpoints."""
    _print_banner("Live Backend API Email Flows Verification")
    print(f"Base API URL     : {base_url}")
    print(f"Target Email     : {email}")
    print(f"Target Flows     : {', '.join(flows)}")

    client = httpx.Client(base_url=base_url, timeout=30.0)
    # Check server availability
    try:
        health_resp = client.get("/health")
        if health_resp.status_code != 200:
            print(f"[ERROR] Backend at {base_url} returned status {health_resp.status_code}")
            return False
    except Exception as exc:
        print(f"[ERROR] Unable to connect to backend at {base_url}: {exc}")
        print("Please start the backend server (e.g. uvicorn app.main:app) before running API flows.")
        return False

    password = "LiveVerification!2026#Secure"
    step_num = 1
    passed_flows = []
    failed_flows = []

    # Verification flow
    if "verification" in flows or "all" in flows:
        _print_step(step_num, "Flow: Email Verification Dispatch")
        step_num += 1
        # Try registration first
        reg_res = client.post(
            "/auth/register",
            json={"full_name": "API Verification User", "email": email, "password": password},
        )
        if reg_res.status_code == 201:
            data = reg_res.json()
            delivery = data.get("email_verification_delivery")
            print(f"  Registration Status   : HTTP 201 (Created)")
            print(f"  Email Delivery Status : {delivery}")
            print(f"  Message               : {data.get('message')}")
            if delivery == "submitted":
                passed_flows.append("verification")
            else:
                failed_flows.append("verification")
        elif reg_res.status_code == 409:
            # User already exists, test resend-verification endpoint
            print("  User already exists. Testing /auth/resend-verification...")
            resend_res = client.post(
                "/auth/resend-verification",
                json={"email": email},
            )
            print(f"  Resend Status         : HTTP {resend_res.status_code}")
            if resend_res.status_code == 200:
                data = resend_res.json()
                delivery = data.get("email_verification_delivery")
                print(f"  Email Delivery Status : {delivery}")
                print(f"  Message               : {data.get('message')}")
                if delivery == "submitted":
                    passed_flows.append("verification")
                else:
                    failed_flows.append("verification")
            else:
                print(f"  Resend Failed         : {resend_res.text}")
                failed_flows.append("verification")
        else:
            print(f"  Registration Failed   : HTTP {reg_res.status_code} - {reg_res.text}")
            failed_flows.append("verification")

    # Password reset flow
    if "password-reset" in flows or "all" in flows:
        _print_step(step_num, "Flow: Password Reset Dispatch")
        step_num += 1
        reset_res = client.post(
            "/auth/forgot-password",
            json={"email": email},
        )
        print(f"  Forgot-Password Status: HTTP {reset_res.status_code}")
        if reset_res.status_code == 200:
            data = reset_res.json()
            delivery = data.get("email_delivery")
            print(f"  Email Delivery Status : {delivery}")
            print(f"  Message               : {data.get('message')}")
            if delivery == "submitted":
                passed_flows.append("password-reset")
            else:
                failed_flows.append("password-reset")
        else:
            print(f"  Forgot-Password Failed: {reset_res.text}")
            failed_flows.append("password-reset")

    # Invitation flow
    if "invitation" in flows or "all" in flows:
        _print_step(step_num, "Flow: Workspace Invitation Dispatch")
        step_num += 1
        # Create an admin user to issue the invitation
        admin_email = f"admin_inviter_{uuid.uuid4().hex[:8]}@handover.local"
        admin_reg = client.post(
            "/auth/register",
            json={"full_name": "Org Admin Inviter", "email": admin_email, "password": password},
        )
        if admin_reg.status_code == 201:
            dev_token = admin_reg.json().get("development_verification_token")
            if dev_token:
                client.post("/auth/verify-email", json={"token": dev_token})
            login_res = client.post("/auth/login", json={"email": admin_email, "password": password})
            if login_res.status_code == 200:
                access_token = login_res.json()["access_token"]
                headers = {"Authorization": f"Bearer {access_token}"}
                # Create org
                org_res = client.post(
                    "/organisations",
                    headers=headers,
                    json={"name": f"Live Test Org {uuid.uuid4().hex[:6]}"},
                )
                if org_res.status_code == 201:
                    org_id = org_res.json()["id"]
                    # Create project
                    proj_res = client.post(
                        f"/organisations/{org_id}/projects",
                        headers=headers,
                        json={"name": "Handover Pilot Project", "description": "Knowledge Transfer"},
                    )
                    if proj_res.status_code == 201:
                        proj_id = proj_res.json()["id"]
                        # Issue invitation
                        inv_res = client.post(
                            f"/organisations/{org_id}/projects/{proj_id}/invitations",
                            headers=headers,
                            json={"email": email, "role_name": "project_member"},
                        )
                        print(f"  Invitation Status     : HTTP {inv_res.status_code}")
                        if inv_res.status_code == 201:
                            data = inv_res.json()
                            delivery = data.get("invitation_delivery")
                            print(f"  Email Delivery Status : {delivery}")
                            if delivery == "submitted":
                                passed_flows.append("invitation")
                            else:
                                failed_flows.append("invitation")
                        else:
                            print(f"  Invitation Failed     : {inv_res.text}")
                            failed_flows.append("invitation")
                    else:
                        print(f"  Project Creation Failed: {proj_res.text}")
                        failed_flows.append("invitation")
                else:
                    print(f"  Org Creation Failed   : {org_res.text}")
                    failed_flows.append("invitation")
            else:
                print(f"  Admin Login Failed    : {login_res.text}")
                failed_flows.append("invitation")
        else:
            print(f"  Admin Register Failed : {admin_reg.text}")
            failed_flows.append("invitation")

    _print_banner("Live API Verification Results")
    print(f"Passed Flows : {passed_flows}")
    print(f"Failed Flows : {failed_flows}")
    return len(failed_flows) == 0 and len(passed_flows) > 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify live transactional email flows with Resend on The Handover platform.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--email",
        default=os.environ.get("RESEND_TEST_RECIPIENT_EMAIL"),
        help="Recipient email address. In Resend sandbox mode, this MUST be the Resend account owner's email.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("API_BASE_URL", "http://127.0.0.1:8000/api/v1"),
        help="Base URL for backend API routes (default: http://127.0.0.1:8000/api/v1).",
    )
    parser.add_argument(
        "--flow",
        choices=["all", "verification", "invitation", "password-reset", "direct"],
        default="all",
        help="Which email flow to execute and verify (default: all).",
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Directly test Python Resend provider without running HTTP server.",
    )

    args = parser.parse_args()

    if not args.email:
        print("[ERROR] Recipient email is required.")
        print("Provide --email <email> or set RESEND_TEST_RECIPIENT_EMAIL environment variable.")
        print("Note: In Resend sandbox mode (onboarding@resend.dev), use your Resend account email.")
        return 1

    settings = Settings()

    if args.direct or args.flow == "direct":
        success = run_direct_verification(args.email, settings)
    else:
        target_flows = ["all"] if args.flow == "all" else [args.flow]
        success = run_api_verification(args.base_url, args.email, target_flows)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

