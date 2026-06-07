from datetime import datetime
from pydantic import BaseModel, EmailStr, field_validator, ConfigDict
import re


# ── Request Schemas ───────────────────────────────────────────────────────────

class UserRegisterRequest(BaseModel):
    email: EmailStr
    full_name: str
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v

    @field_validator("full_name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Full name cannot be empty")
        return v.strip()


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


# ── Response Schemas ──────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    """Safe user representation — never exposes hashed_password."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class MessageResponse(BaseModel):
    """Generic success message wrapper."""
    message: str
    success: bool = True
