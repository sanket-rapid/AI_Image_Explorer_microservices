from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import or_
from models import History, User
from schemas import HistoryResponse
from database import get_db
from dependencies import get_current_user
from typing import Optional, List
import redis
import json
import logging
from dotenv import load_dotenv
import os

load_dotenv()
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")

redis_client = redis.Redis(host=REDIS_HOST, port=int(REDIS_PORT), decode_responses=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", response_model=List[HistoryResponse])
async def get_dashboard(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    type: Optional[str] = Query(None, description="Filter by type (search/image)"),
    keyword: Optional[str] = Query(None, description="Filter by keyword in query or result"),
    date_start: Optional[str] = Query(None, description="Filter by start date (YYYY-MM-DD)"),
    date_end: Optional[str] = Query(None, description="Filter by end date (YYYY-MM-DD)")
):
    cache_key = f"dashboard:user:{user.id}:type:{type or 'all'}:keyword:{keyword or 'none'}:start:{date_start or 'none'}:end:{date_end or 'none'}"
    cached_data = redis_client.get(cache_key)
    if cached_data:
        history_data = json.loads(cached_data)
        if history_data:  # Only return cached data if non-empty
            logger.info(f"Returning cached history for user {user.id}")
            return history_data
        logger.info(f"Cached data empty for user {user.id}, querying database")

    query = db.query(History)
    if user.role != "admin":
        query = query.filter(History.user_id == user.id)
    if type and type != "all":
        query = query.filter(History.type == type)
    if keyword:
        query = query.filter(or_(History.query.contains(keyword), History.result.contains(keyword)))
    if date_start:
        query = query.filter(History.created_at >= date_start)
    if date_end:
        query = query.filter(History.created_at <= date_end)
    
    history = query.all()
    history_data = [
        {
            "id": h.id,
            "user_id": h.user_id,
            "type": h.type,
            "query": h.query,
            "result": h.result,
            "created_at": h.created_at.isoformat(),
            "meta_data": h.meta_data
        } for h in history
    ]
    redis_client.setex(cache_key, 3600, json.dumps(history_data))
    logger.info(f"User {user.username} fetched dashboard history")
    return history_data

@app.put("/dashboard/{id}", response_model=HistoryResponse)
async def update_dashboard(
    id: int,
    update_data: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(History)
    if user.role != "admin":
        query = query.filter(History.user_id == user.id)
    history = query.filter(History.id == id).first()
    if not history:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    if 'query' in update_data:
        history.query = update_data['query']
    if 'result' in update_data:
        history.result = update_data['result']
    
    db.commit()
    db.refresh(history)
    
    redis_client.delete(f"dashboard:user:{user.id}:*")
    logger.info(f"User {user.username} updated history entry {id}")
    return {
        "id": history.id,
        "user_id": history.user_id,
        "type": history.type,
        "query": history.query,
        "result": history.result,
        "created_at": history.created_at.isoformat(),
        "meta_data": history.meta_data
    }

@app.delete("/dashboard/{id}")
async def delete_dashboard(
    id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(History)
    if user.role != "admin":
        query = query.filter(History.user_id == user.id)
    history = query.filter(History.id == id).first()
    if not history:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    db.delete(history)
    db.commit()
    
    redis_client.delete(f"dashboard:user:{user.id}:*")
    logger.info(f"User {user.username} deleted history entry {id}")
    return {"detail": "Entry deleted"}