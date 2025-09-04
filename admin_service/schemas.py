from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "user"  # Default to user role

class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    class Config:
        orm_mode = True  # Enables SQLAlchemy ORM compatibility

class UserUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None

class HistoryResponse(BaseModel):
    id: int
    user_id: int
    type: str
    query: str
    result: str
    created_at: datetime
    meta_data: Optional[str] = None
    class Config:
        orm_mode = True