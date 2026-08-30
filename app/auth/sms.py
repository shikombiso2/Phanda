import httpx

from app.core.config import get_settings


async def send_otp_sms(phone_number: str, otp_code: str) -> bool:
    settings = get_settings()
    if settings.otp_dev_mode or settings.sms_provider == "none":
        return False
    if not settings.sms_api_url or not settings.sms_api_key:
        return False

    payload = {
        "to": phone_number,
        "from": settings.sms_from,
        "message": f"Your Phanda verification code is {otp_code}",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            settings.sms_api_url,
            headers={"Authorization": f"Bearer {settings.sms_api_key}"},
            json=payload,
        )
        response.raise_for_status()
    return True
