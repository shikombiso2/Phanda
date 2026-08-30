import unittest
from unittest.mock import patch

from app.auth.sms import send_otp_sms


class SmsTests(unittest.IsolatedAsyncioTestCase):
    async def test_dev_mode_does_not_send_sms(self):
        with patch("app.auth.sms.get_settings") as get_settings:
            get_settings.return_value.otp_dev_mode = True
            get_settings.return_value.sms_provider = "generic"
            get_settings.return_value.sms_api_url = "https://sms.example/send"
            get_settings.return_value.sms_api_key = "secret"

            sent = await send_otp_sms("+27123456789", "123456")

        self.assertFalse(sent)


if __name__ == "__main__":
    unittest.main()

