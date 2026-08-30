from pydantic import BaseModel, Field


class OtpRequestIn(BaseModel):
    phone_number: str = Field(min_length=8, max_length=32)


class OtpRequestOut(BaseModel):
    message: str
    dev_otp: str | None = None


class OtpVerifyIn(BaseModel):
    phone_number: str = Field(min_length=8, max_length=32)
    otp_code: str = Field(min_length=4, max_length=12)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

