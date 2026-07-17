from pydantic import BaseModel, Field, field_validator


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Name cannot be blank")
        return name

    @field_validator("email")
    @classmethod
    def email_must_be_valid(cls, value: str) -> str:
        email = value.strip().lower()
        if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            raise ValueError("Email is invalid")
        return email


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def email_must_be_valid(cls, value: str) -> str:
        return value.strip().lower()


class AccountDeleteRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=32)

    @field_validator("confirmation")
    @classmethod
    def confirmation_must_match(cls, value: str) -> str:
        if value.strip() != "DELETE":
            raise ValueError("Confirmation must be DELETE")
        return "DELETE"
