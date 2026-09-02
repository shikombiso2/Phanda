from app.core.email import EmailAttachment, EmailOutcomeUnknown, send_email

__all__ = ["EmailOutcomeUnknown", "send_application_email"]


async def send_application_email(
    *,
    to_email: str,
    subject: str,
    body: str,
    cv_bytes: bytes,
    cv_filename: str,
    cover_letter_bytes: bytes | None = None,
    reply_to: str | None = None,
) -> None:
    """Send actual PDF attachments; never include private storage locations in email."""
    attachments = [EmailAttachment(filename=cv_filename, content=cv_bytes)]
    if cover_letter_bytes:
        attachments.append(EmailAttachment(filename="Cover_Letter.pdf", content=cover_letter_bytes))
    await send_email(to=to_email, subject=subject, text=body, reply_to=reply_to, attachments=attachments)
