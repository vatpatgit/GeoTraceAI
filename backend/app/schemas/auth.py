from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class LoginRequest(BaseModel):
    """Schema for login request."""
    email: EmailStr | str
    password: str

class TokenResponse(BaseModel):
    """Schema for authentication token response."""
    access_token: str
    token_type: str = 'bearer'

class UserResponse(BaseModel):
    """Schema for user response."""
    id: UUID
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12)
    role: str = "viewer"


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None


class UserRoleUpdate(BaseModel):
    role: str


class UserStatusUpdate(BaseModel):
    is_active: bool
