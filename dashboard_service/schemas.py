from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class HistoryResponse(BaseModel):
    id: int
    user_id: int
    type: str
    query: str
    result: Optional[str] = None
    created_at: datetime
    meta_data: Optional[str] = None
    class Config:
        orm_mode = True