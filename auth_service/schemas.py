from pydantic import BaseModel

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

class Token(BaseModel):
    access_token: str
    token_type: str