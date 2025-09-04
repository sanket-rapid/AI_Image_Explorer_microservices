from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="user")  # user or admin

class History(Base):
    __tablename__ = "history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    type = Column(String)  # 'search' or 'image'
    query = Column(String)
    result = Column(String)  # JSON string for search summary or image URL
    created_at = Column(DateTime, default=datetime.utcnow)
    meta_data = Column(String, nullable=True)  # Renamed from metadata