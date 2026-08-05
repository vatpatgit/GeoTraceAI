from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr

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
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
