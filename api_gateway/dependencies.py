from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from pydantic import BaseModel
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM")

security = HTTPBearer()

class User(BaseModel):
    id: int
    username: str
    role: str

async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        user_id: int = payload.get("id", 0)  # Ensure id is included in token
        if username is None or role is None:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return User(id=user_id, username=username, role=role)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")