"""Responsive HTML and plain-text transactional email templates for The Handover."""

from __future__ import annotations

import html
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RenderedEmailTemplate:
    """Rendered subject, HTML, and plain-text alternatives."""

    subject: str
    html_body: str
    text_body: str


def _wrap_html_layout(*, preheader: str, heading: str, body_html: str) -> str:
    safe_preheader = html.escape(preheader)
    safe_heading = html.escape(heading)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{safe_heading}</title>
</head>
<body style="margin:0;padding:0;background-color:#F4F7F5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1A2421;">
  <span style="display:none;max-height:0;overflow:hidden;opacity:0;">{safe_preheader}</span>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#F4F7F5;padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:580px;background-color:#FFFFFF;border:1px solid #DCE5DF;border-radius:12px;overflow:hidden;">
          <tr>
            <td style="background-color:#1E3F35;padding:24px 32px;border-bottom:3px solid #2E6F5E;">
              <div style="font-size:13px;letter-spacing:0.08em;text-transform:uppercase;color:#A7D7C5;font-weight:600;">The Handover</div>
              <div style="font-size:19px;color:#FFFFFF;font-weight:600;margin-top:4px;">{safe_heading}</div>
            </td>
          </tr>
          <tr>
            <td style="padding:32px;">
              {body_html}
            </td>
          </tr>
          <tr>
            <td style="background-color:#F8FAF9;padding:20px 32px;border-top:1px solid #E6ECE8;font-size:12px;line-height:1.5;color:#5A6B65;">
              <strong style="color:#2D3B36;">The Handover</strong> · Intelligent Project Knowledge Reconstruction &amp; Handover Platform<br/>
              Prevent Critical Knowledge From Leaving With People.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def render_email_verification(
    *,
    verification_url: str,
    recipient_name: str,
    expires_hours: int = 24,
) -> RenderedEmailTemplate:
    """Render both verification and resend emails using one canonical template."""
    subject = "Verify your Handover account"
    safe_name = html.escape(recipient_name or "there")
    safe_url = html.escape(verification_url, quote=True)

    body_html = f"""
      <p style="margin:0 0 16px;font-size:15px;line-height:1.6;">Hello {safe_name},</p>
      <p style="margin:0 0 20px;font-size:15px;line-height:1.6;">
        Please verify your email address to activate your account and access your assigned organisations and project workspaces on <strong>The Handover</strong>.
      </p>
      <table role="presentation" cellspacing="0" cellpadding="0" style="margin:24px 0;">
        <tr>
          <td style="border-radius:8px;background-color:#245C4F;">
            <a href="{safe_url}" target="_blank" rel="noopener noreferrer" style="display:inline-block;padding:13px 26px;font-size:15px;font-weight:600;color:#FFFFFF;text-decoration:none;">
              Verify Email Address
            </a>
          </td>
        </tr>
      </table>
      <p style="margin:0 0 12px;font-size:13px;line-height:1.6;color:#4B5B55;">
        <strong>Expiration notice:</strong> This verification link expires in {expires_hours} hours. If it expires, you can request a new verification link from the sign-in or verification page.
      </p>
      <p style="margin:0 0 16px;font-size:13px;line-height:1.6;color:#4B5B55;">
        <strong>Security notice:</strong> If you did not create a Handover account, you can safely ignore this message. No project access is granted until verification is completed.
      </p>
      <p style="margin:20px 0 6px;font-size:12px;color:#5A6B65;">If the button above does not work, copy and paste this link into your browser:</p>
      <p style="margin:0;font-size:12px;line-height:1.5;word-break:break-all;color:#1E5288;">{safe_url}</p>
    """
    html_body = _wrap_html_layout(
        preheader="Verify your email address to unlock your Handover workspace.",
        heading="Verify Your Account",
        body_html=body_html,
    )
    text_body = (
        f"Hello {recipient_name or 'there'},\n\n"
        "Please verify your email address to activate your account and access your assigned "
        "organisations and project workspaces on The Handover.\n\n"
        f"Verify your email: {verification_url}\n\n"
        f"Expiration notice: This link expires in {expires_hours} hours.\n"
        "Security notice: If you did not create a Handover account, you can safely ignore this email.\n"
    )
    return RenderedEmailTemplate(subject=subject, html_body=html_body, text_body=text_body)


def render_project_invitation(
    *,
    invitation_url: str,
    organisation_name: str,
    project_name: str,
    project_role_display: str,
    inviter_name: str | None,
    expires_in_hours: int,
) -> RenderedEmailTemplate:
    """Render project invitation email with org, project, role, expiry, and existing-account guidance."""
    subject = "You've been invited to a Handover project"
    safe_org = html.escape(organisation_name)
    safe_project = html.escape(project_name)
    safe_role = html.escape(project_role_display)
    safe_inviter = html.escape(inviter_name) if inviter_name else "A project manager"
    safe_url = html.escape(invitation_url, quote=True)
    expiry_days = max(1, expires_in_hours // 24) if expires_in_hours >= 24 else None
    expiry_text = (
        f"{expiry_days} day{'s' if expiry_days != 1 else ''}"
        if expiry_days is not None
        else f"{expires_in_hours} hour{'s' if expires_in_hours != 1 else ''}"
    )

    body_html = f"""
      <p style="margin:0 0 16px;font-size:15px;line-height:1.6;">
        <strong>{safe_inviter}</strong> has invited you to join the project <strong>{safe_project}</strong> in <strong>{safe_org}</strong> on The Handover.
      </p>
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:18px 0;background-color:#F4F8F6;border:1px solid #D9E5DF;border-radius:8px;">
        <tr>
          <td style="padding:16px 20px;font-size:14px;line-height:1.6;">
            <div><strong>Organisation:</strong> {safe_org}</div>
            <div><strong>Project:</strong> {safe_project}</div>
            <div><strong>Assigned Project Role:</strong> {safe_role}</div>
            <div><strong>Invitation Expires:</strong> In {expiry_text}</div>
          </td>
        </tr>
      </table>
      <table role="presentation" cellspacing="0" cellpadding="0" style="margin:24px 0;">
        <tr>
          <td style="border-radius:8px;background-color:#245C4F;">
            <a href="{safe_url}" target="_blank" rel="noopener noreferrer" style="display:inline-block;padding:13px 26px;font-size:15px;font-weight:600;color:#FFFFFF;text-decoration:none;">
              View &amp; Accept Invitation
            </a>
          </td>
        </tr>
      </table>
      <p style="margin:0 0 12px;font-size:13px;line-height:1.6;color:#4B5B55;">
        <strong>Already have a Handover account?</strong> Sign in with your existing account from the invitation page to accept and add this project to your workspace without creating a duplicate account.
      </p>
      <p style="margin:20px 0 6px;font-size:12px;color:#5A6B65;">If the button above does not work, copy and paste this link into your browser:</p>
      <p style="margin:0;font-size:12px;line-height:1.5;word-break:break-all;color:#1E5288;">{safe_url}</p>
    """
    html_body = _wrap_html_layout(
        preheader=f"Invitation to {project_name} ({organisation_name}) as {project_role_display}.",
        heading="Project Invitation",
        body_html=body_html,
    )
    text_body = (
        f"{inviter_name or 'A project manager'} has invited you to join the project '{project_name}' "
        f"in '{organisation_name}' on The Handover.\n\n"
        f"Assigned Project Role: {project_role_display}\n"
        f"Invitation Expires: In {expiry_text}\n\n"
        f"Accept your invitation: {invitation_url}\n\n"
        "Already have a Handover account? Sign in from the invitation link to accept without creating a new account.\n"
    )
    return RenderedEmailTemplate(subject=subject, html_body=html_body, text_body=text_body)


def render_organisation_invitation(
    *,
    invitation_url: str,
    organisation_name: str,
    role_display: str,
    inviter_name: str | None,
    expires_in_hours: int,
) -> RenderedEmailTemplate:
    """Render organisation-level invitation email."""
    subject = f"You've been invited to join {organisation_name} on The Handover"
    safe_org = html.escape(organisation_name)
    safe_role = html.escape(role_display)
    safe_inviter = html.escape(inviter_name) if inviter_name else "An organisation administrator"
    safe_url = html.escape(invitation_url, quote=True)

    body_html = f"""
      <p style="margin:0 0 16px;font-size:15px;line-height:1.6;">
        <strong>{safe_inviter}</strong> has invited you to join <strong>{safe_org}</strong> on The Handover with the role <strong>{safe_role}</strong>.
      </p>
      <table role="presentation" cellspacing="0" cellpadding="0" style="margin:24px 0;">
        <tr>
          <td style="border-radius:8px;background-color:#245C4F;">
            <a href="{safe_url}" target="_blank" rel="noopener noreferrer" style="display:inline-block;padding:13px 26px;font-size:15px;font-weight:600;color:#FFFFFF;text-decoration:none;">
              Accept Organisation Invitation
            </a>
          </td>
        </tr>
      </table>
      <p style="margin:0 0 12px;font-size:13px;line-height:1.6;color:#4B5B55;">
        This invitation expires in {expires_in_hours} hours.
      </p>
      <p style="margin:0;font-size:12px;line-height:1.5;word-break:break-all;color:#1E5288;">{safe_url}</p>
    """
    html_body = _wrap_html_layout(
        preheader=f"Invitation to join {organisation_name} on The Handover.",
        heading="Organisation Invitation",
        body_html=body_html,
    )
    text_body = (
        f"{inviter_name or 'An organisation administrator'} invited you to join {organisation_name} "
        f"on The Handover as {role_display}.\n\n"
        f"Accept invitation: {invitation_url}\n"
        f"Expires in {expires_in_hours} hours.\n"
    )
    return RenderedEmailTemplate(subject=subject, html_body=html_body, text_body=text_body)
