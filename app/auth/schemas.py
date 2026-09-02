from pydantic import BaseModel, EmailStr, Field, model_validator


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    confirm_password: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def passwords_match(self) -> "RegisterIn":
        if self.password != self.confirm_password:
            raise ValueError("password and confirm_password must match")
        return self


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class GoogleAuthIn(BaseModel):
    id_token: str = Field(min_length=1)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutIn(BaseModel):
    refresh_token: str = Field(min_length=1)


class AuthTokensOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    is_new_user: bool
