import httpx

from app.core.config import get_settings


async def send_application_email(to_email: str, subject: str, body: str, cv_url: str, cover_letter_url: str) -> bool:
    settings = get_settings()
    if settings.email_provider == "sendgrid" and settings.sendgrid_api_key:
        payload = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": settings.email_from},
            "subject": subject,
            "content": [{"type": "text/plain", "value": f"{body}\n\nCV: {cv_url}\nCover letter: {cover_letter_url}"}],
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {settings.sendgrid_api_key}"},
                json=payload,
            )
            response.raise_for_status()
        return True

    if settings.email_provider == "mailgun" and settings.mailgun_api_key and settings.mailgun_domain:
        auth = ("api", settings.mailgun_api_key)
        data = {
            "from": settings.email_from,
            "to": to_email,
            "subject": subject,
            "text": f"{body}\n\nCV: {cv_url}\nCover letter: {cover_letter_url}",
        }
        url = f"https://api.mailgun.net/v3/{settings.mailgun_domain}/messages"
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(url, auth=auth, data=data)
            response.raise_for_status()
        return True

    return False
