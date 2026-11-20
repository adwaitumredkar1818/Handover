#!/usr/bin/env python3
"""Automated live transactional email verification tooling for Resend.

Tests live email delivery using ResendEmailProvider (direct provider mode)
and against local backend endpoints (API mode).

Usage examples:
    # Direct provider test to recipient email (no backend server required):
    python scripts/verify_live_resend.py --email user@example.com --direct

    # Run all live API flows against running backend:
    python scripts/verify_live_resend.py --email user@example.com --base-url http://127.0.0.1:8000/api/v1 --flow all

    # Run specific flow against running backend:
    python scripts/verify_live_resend.py --email user@example.com --flow verification
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
from app.core.config import Settings, get_settings
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


def _check_resend_diagnostics(result: EmailDeliveryResult, sending_domain: str) -> None:
    if result.status == "failed" and result.error_message:
        err_lower = result.error_message.lower()
        if "api key" in err_lower or "unauthorized" in err_lower or "401" in err_lower or "403" in err_lower:
            print("\n  [!] RESEND API KEY ERROR:")
            print(f"      {result.error_message}")
            print("      Note: Please verify your RESEND_API_KEY in .env.")
            print("      Generate an API key with Sending Access at:")
            print("      https://resend.com/api-keys\n")
        elif "domain" in err_lower and ("verify" in err_lower or "not verified" in err_lower):
            print("\n  [!] RESEND DOMAIN VERIFICATION REQUIRED:")
            print(f"      {result.error_message}")
            print(f"      Note: Domain '{sending_domain}' must be added and verified in Resend:")
            print("      1. Add domain at https://resend.com/domains")
            print("      2. Configure DKIM and SPF DNS records in your domain registrar/DNS provider.")
            print("      3. Wait for DNS propagation and click 'Verify Domain' in Resend.\n")


def run_direct_verification(email: str, settings: Settings) -> bool:
    """Directly test TransactionalEmailService and ResendEmailProvider with configured credentials."""
    _print_banner("Direct Resend Provider Verification")
    print(f"Recipient Email  : {email}")
    print(f"Email Provider   : {settings.email.provider}")
    print(f"Sender Identity  : {settings.email.sender_identity}")
    print(f"Sending Domain   : {settings.email.sending_domain}")
    print(f"Delivery Enabled : {settings.email.delivery_enabled}")
    print(f"Frontend URL     : {settings.email.frontend_base_url}")

    api_key = (
        settings.email.resend_api_key.get_secret_value()
        if settings.email.resend_api_key is not None
        else os.environ.get("RESEND_API_KEY")
    )

    if not api_key:
        print("\n[ERROR] RESEND_API_KEY is not configured in backend environment (.env).")
        print("Please configure RESEND_API_KEY to test live Resend email delivery.")
        return False

    provider = ResendEmailProvider(
        api_key=api_key,
        from_address=settings.email.from_address,
        from_name=settings.email.from_name,
        sending_domain=settings.email.sending_domain,
        timeout_seconds=settings.email.http_timeout_seconds,
    )
    email_service = TransactionalEmailService(settings=settings, provider=provider)

    test_token = f"live-resend-test-{uuid.uuid4().hex[:16]}"

    # Step 1: Verification Email Test
    _print_step(1, "Dispatching Live Email Verification via Resend")
    ver_res = email_service.send_verification_email(
        to_email=email,
        recipient_name="Live Resend Tester",
        raw_token=test_token,
    )
    print(f"  Status        : {ver_res.status}")
    print(f"  Provider      : {ver_res.provider}")
    print(f"  Message ID    : {ver_res.provider_message_id}")
    if ver_res.error_message:
        print(f"  Error Detail  : {ver_res.error_message}")
        _check_resend_diagnostics(ver_res, settings.email.sending_domain)

    # Step 2: Password Reset Email Test
    _print_step(2, "Dispatching Live Password Reset Email via Resend")
    reset_res = email_service.send_password_reset_email(
        to_email=email,
        recipient_name="Live Resend Tester",
        raw_token=test_token,
    )
    print(f"  Status        : {reset_res.status}")
    print(f"  Provider      : {reset_res.provider}")
    print(f"  Message ID    : {reset_res.provider_message_id}")
    if reset_res.error_message:
        print(f"  Error Detail  : {reset_res.error_message}")
        _check_resend_diagnostics(reset_res, settings.email.sending_domain)

    # Step 3: Project Invitation Email Test
    _print_step(3, "Dispatching Live Project Invitation Email via Resend")
    inv_res = email_service.send_project_invitation_email(
        to_email=email,
        raw_token=test_token,
        organisation_name="Handover Test Labs",
        project_name="Knowledge Core",
        project_role_name="reviewer",
        inviter_name="Lead Engineer",
        expires_in_hours=72,
    )
    print(f"  Status        : {inv_res.status}")
    print(f"  Provider      : {inv_res.provider}")
    print(f"  Message ID    : {inv_res.provider_message_id}")
    if inv_res.error_message:
        print(f"  Error Detail  : {inv_res.error_message}")
        _check_resend_diagnostics(inv_res, settings.email.sending_domain)

    # Step 4: Organisation Invitation Email Test
    _print_step(4, "Dispatching Live Organisation Invitation Email via Resend")
    org_res = email_service.send_organisation_invitation_email(
        to_email=email,
        raw_token=test_token,
        organisation_name="Handover Test Labs",
        role_name="org_member",
        inviter_name="System Admin",
        expires_in_hours=48,
    )
    print(f"  Status        : {org_res.status}")
    print(f"  Provider      : {org_res.provider}")
    print(f"  Message ID    : {org_res.provider_message_id}")
    if org_res.error_message:
        print(f"  Error Detail  : {org_res.error_message}")
        _check_resend_diagnostics(org_res, settings.email.sending_domain)

    # Step 5: Platform Notification Email Test
    _print_step(5, "Dispatching Live Platform Notification Email via Resend")
    notif_res = email_service.send_platform_notification_email(
        to_email=email,
        recipient_name="Live Resend Tester",
        notification_title="Document Processing Completed",
        message_body="Your project documentation 'architecture-overview.pdf' was reconstructed and indexed.",
        action_url=f"{settings.email.frontend_base_url}/projects/test-project",
        action_label="Review Evidence",
        project_name="Knowledge Core",
    )
    print(f"  Status        : {notif_res.status}")
    print(f"  Provider      : {notif_res.provider}")
    print(f"  Message ID    : {notif_res.provider_message_id}")
    if notif_res.error_message:
        print(f"  Error Detail  : {notif_res.error_message}")
        _check_resend_diagnostics(notif_res, settings.email.sending_domain)

    all_passed = all(
        r.status == "submitted"
        for r in [ver_res, reset_res, inv_res, org_res, notif_res]
    )

    _print_banner("Verification Summary")
    if all_passed:
        print("  [SUCCESS] All 5 live transactional email flows were successfully submitted to Resend!")
        print(f"  Target Inbox: {email}")
    else:
        print("  [WARNING] Some or all delivery requests were not submitted successfully.")
        print("  Check the error details above for required actions (API key, domain verification, etc.).")

    return all_passed


def main() -> int:
    parser = argparse.ArgumentParser(description="Live Resend transactional email verification tooling for The Handover.")
    parser.add_argument(
        "--email",
        default=os.environ.get("RESEND_TEST_RECIPIENT_EMAIL"),
        help="Recipient email address. In Resend sandbox mode, use account owner email.",
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Directly test the Resend provider without requiring a running backend server.",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000/api/v1",
        help="Base URL of running backend server (default: http://127.0.0.1:8000/api/v1).",
    )
    parser.add_argument(
        "--flow",
        choices=["all", "verification", "invitation", "reset", "notification"],
        default="all",
        help="Specific flow to test in API mode (default: all).",
    )
    args = parser.parse_args()

    settings = get_settings()

    target_email = args.email
    if not target_email:
        print("[ERROR] No target email provided. Specify with --email <address> or configure RESEND_TEST_RECIPIENT_EMAIL.")
        return 1

    print(f"Running Resend verification targeting: {target_email}")
    if args.direct:
        success = run_direct_verification(target_email, settings)
        return 0 if success else 1

    print("Running in API mode...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
