"""Generic transactional email sending.

One provider-neutral primitive used by every part of the app that sends
email — today that is application emails to employers; tomorrow it might be
account-notice or password-changed emails. Before this module existed, the
SendGrid/Mailgun switch lived only inside ``app/applications/email.py``,
coupled to CV attachments, so a second caller would have had to duplicate it.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

import httpx

from app.core.config import get_settings


class EmailOutcomeUnknown(RuntimeError):
    """The provider may have accepted the message before the connection was lost.

    Callers must not blindly retry on this: a retry could send a duplicate
    message if the provider actually did accept it before the timeout/5xx.
    """


@dataclass(frozen=True)
class EmailAttachment:
    filename: str
    content: bytes
    content_type: str = "application/pdf"


async def send_email(
    *,
    to: str,
    subject: str,
    text: str,
    html: str | None = None,
    reply_to: str | None = None,
    attachments: list[EmailAttachment] | None = None,
) -> None:
    settings = get_settings()
    attachments = attachments or []

    if settings.email_provider == "sendgrid" and settings.sendgrid_api_key:
        await _send_via_sendgrid(settings, to=to, subject=subject, text=text, html=html, reply_to=reply_to, attachments=attachments)
        return
    if settings.email_provider == "mailgun" and settings.mailgun_api_key and settings.mailgun_domain:
        await _send_via_mailgun(settings, to=to, subject=subject, text=text, html=html, reply_to=reply_to, attachments=attachments)
        return
    raise RuntimeError("email_not_configured")


async def _send_via_sendgrid(
    settings, *, to: str, subject: str, text: str, html: str | None, reply_to: str | None, attachments: list[EmailAttachment]
) -> None:
    content = [{"type": "text/plain", "value": text}]
    if html:
        content.append({"type": "text/html", "value": html})
    payload: dict[str, object] = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": settings.email_from},
        "subject": subject,
        "content": content,
    }
    if reply_to:
        payload["reply_to"] = {"email": reply_to}
    if attachments:
        payload["attachments"] = [_sendgrid_attachment(a) for a in attachments]
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {settings.sendgrid_api_key}"},
                json=payload,
            )
            if response.status_code >= 500:
                raise EmailOutcomeUnknown("sendgrid_server_error")
            response.raise_for_status()
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        raise EmailOutcomeUnknown("sendgrid_transport_error") from exc


async def _send_via_mailgun(
    settings, *, to: str, subject: str, text: str, html: str | None, reply_to: str | None, attachments: list[EmailAttachment]
) -> None:
    data: dict[str, str] = {"from": settings.email_from, "to": to, "subject": subject, "text": text}
    if html:
        data["html"] = html
    if reply_to:
        data["h:Reply-To"] = reply_to
    files = [("attachment", (a.filename, a.content, a.content_type)) for a in attachments]
    url = f"https://api.mailgun.net/v3/{settings.mailgun_domain}/messages"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(url, auth=("api", settings.mailgun_api_key), data=data, files=files or None)
            if response.status_code >= 500:
                raise EmailOutcomeUnknown("mailgun_server_error")
            response.raise_for_status()
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        raise EmailOutcomeUnknown("mailgun_transport_error") from exc


def _sendgrid_attachment(attachment: EmailAttachment) -> dict[str, str]:
    return {
        "content": base64.b64encode(attachment.content).decode("ascii"),
        "type": attachment.content_type,
        "filename": attachment.filename,
        "disposition": "attachment",
    }
