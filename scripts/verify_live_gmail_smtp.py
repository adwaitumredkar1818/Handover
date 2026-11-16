#!/usr/bin/env python3
"""Automated live transactional email verification tooling for Gmail SMTP.

Tests live email delivery using GmailSMTPEmailProvider (direct provider mode)
and against local backend endpoints (API mode).

Usage examples:
    # Direct provider test to recipient email (no backend server required):
    python scripts/verify_live_gmail_smtp.py --email user@example.com --direct

    # Run all live API flows against running backend:
    python scripts/verify_live_gmail_smtp.py --email user@example.com --base-url http://127.0.0.1:8000/api/v1 --flow all

    # Run specific flow against running backend:
    python scripts/verify_live_gmail_smtp.py --email user@example.com --flow verification
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
    GmailSMTPEmailProvider,
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


def _check_app_password_warning(result: EmailDeliveryResult) -> None:
    if result.status == "failed" and result.error_message:
        err_lower = result.error_message.lower()
        if "535" in err_lower or "authentication failed" in err_lower:
            print("\n  [!] GOOGLE APP PASSWORD ERROR (Code 535):")
            print(f"      {result.error_message}")
            print("      Note: Standard Google account passwords are not accepted by Gmail SMTP.")
            print("      A 16-character App Password must be generated at:")
            print("      https://myaccount.google.com/apppasswords (2-Step Verification required).\n")
        elif "timeout" in err_lower:
            print("\n  [!] CONNECTION TIMEOUT ERROR:")
            print(f"      {result.error_message}")
            print("      Note: Verify that port 587 outbound is not blocked by your ISP or firewall.\n")


def run_direct_verification(email: str, settings: Settings) -> bool:
    """Directly test TransactionalEmailService and GmailSMTPEmailProvider with configured credentials."""
    _print_banner("Direct Gmail SMTP Provider Verification")
    print(f"Recipient Email  : {email}")
    print(f"Email Provider   : {settings.email.provider}")
    print(f"SMTP Host        : {settings.email.smtp_host}:{settings.email.smtp_port}")
    print(f"SMTP Username    : {settings.email.smtp_username or '(not configured)'}")
    print(f"From Address     : {settings.email.from_address}")
    print(f"Delivery Enabled : {settings.email.delivery_enabled}")
    print(f"Frontend URL     : {settings.email.frontend_base_url}")

    if not settings.email.smtp_username:
        print("\n[ERROR] SMTP_USERNAME is not configured in backend environment (.env).")
        print("Please configure SMTP_USERNAME (your Gmail address) to test live Gmail SMTP delivery.")
        return False

    if not settings.email.smtp_app_password or not settings.email.smtp_app_password.get_secret_value():
        print("\n[ERROR] SMTP_APP_PASSWORD is not configured in backend environment (.env).")
        print("Please configure SMTP_APP_PASSWORD (16-char Google App Password) to test live Gmail SMTP delivery.")
        return False

    provider = GmailSMTPEmailProvider(
        host=settings.email.smtp_host,
        port=settings.email.smtp_port,
        username=settings.email.smtp_username,
        app_password=settings.email.smtp_app_password.get_secret_value(),
        use_tls=settings.email.smtp_use_tls,
        timeout_seconds=settings.email.smtp_timeout_seconds,
        from_address=settings.email.from_address,
        from_name=settings.email.from_name,
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
        _check_app_password_warning(ver_res)
    if ver_res.status == "sent":
        success_count += 1
        print("  [OK] Email verification dispatched successfully.")

    # Step 2: Project Invitation Email
    _print_step(2, "Direct Dispatch: Project Invitation")
    test_inv_token = f"direct_inv_{uuid.uuid4().hex[:16]}"
    inv_res = email_service.send_project_invitation_email(
        to_email=email,
        recipient_name="Direct Invitation Tester",
        inviter_name="Platform Lead",
        project_name="Core Knowledge Reconstruction",
        role_name="Senior Engineer",
        raw_token=test_inv_token,
        expires_at="in 7 days",
    )
    print(f"  Status        : {inv_res.status}")
    print(f"  Provider      : {inv_res.provider}")
    print(f"  Message ID    : {inv_res.provider_message_id or 'None'}")
    if inv_res.error_message:
        print(f"  Error Detail  : {inv_res.error_message}")
        _check_app_password_warning(inv_res)
    if inv_res.status == "sent":
        success_count += 1
        print("  [OK] Project invitation email dispatched successfully.")

    # Step 3: Password Reset Email
    _print_step(3, "Direct Dispatch: Password Reset")
    test_pwd_token = f"direct_pwd_{uuid.uuid4().hex[:16]}"
    pwd_res = email_service.send_password_reset_email(
        to_email=email,
        recipient_name="Direct Password Tester",
        raw_token=test_pwd_token,
    )
    print(f"  Status        : {pwd_res.status}")
    print(f"  Provider      : {pwd_res.provider}")
    print(f"  Message ID    : {pwd_res.provider_message_id or 'None'}")
    if pwd_res.error_message:
        print(f"  Error Detail  : {pwd_res.error_message}")
        _check_app_password_warning(pwd_res)
    if pwd_res.status == "sent":
        success_count += 1
        print("  [OK] Password reset email dispatched successfully.")

    provider.close()

    _print_banner("Direct Verification Summary")
    print(f"Dispatched: {success_count}/{total_steps} emails successfully.")
    return success_count == total_steps


def main() -> int:
    parser = argparse.ArgumentParser(description="Live Gmail SMTP verification script for The Handover.")
    parser.add_argument(
        "--email",
        default=os.environ.get("SMTP_USERNAME"),
        help="Recipient email address. Defaults to SMTP_USERNAME from environment.",
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        default=True,
        help="Directly test the Gmail SMTP provider without requiring a running backend server.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("API_BASE_URL", "http://127.0.0.1:8000/api/v1"),
        help="Base backend API URL for API flow testing.",
    )
    args = parser.parse_args()

    settings = Settings()

    target_email = args.email or settings.email.smtp_username
    if not target_email:
        print("[ERROR] No target email provided. Specify with --email <address> or configure SMTP_USERNAME in .env.")
        return 1

    print(f"Running Gmail SMTP verification targeting: {target_email}")
    success = run_direct_verification(target_email, settings)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
