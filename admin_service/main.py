from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from models import User, History
from schemas import UserResponse, UserCreate, HistoryResponse
from database import get_db
from dependencies import get_admin_user
from passlib.context import CryptContext
from typing import Optional, List
import redis
import logging
from datetime import datetime, timedelta
import json
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")

# Initialize Redis
redis_client = redis.Redis(host=REDIS_HOST, port=int(REDIS_PORT), decode_responses=True)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@app.get("/users", response_model=List[UserResponse])
async def get_all_users(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    role_filter: Optional[str] = Query(None, description="Filter by role (user/admin)")
):
    """Get all users (admin only)"""
    cache_key = f"admin:users:skip{skip}:limit{limit}:role{role_filter or 'all'}"
    cached_users = redis_client.get(cache_key)
    if cached_users:
        logger.info(f"Returning cached user list for {cache_key}")
        return json.loads(cached_users)

    query = db.query(User)
    if role_filter:
        query = query.filter(User.role == role_filter)
    
    users = query.offset(skip).limit(limit).all()
    redis_client.setex(cache_key, 3600, json.dumps([user.__dict__ for user in users]))
    logger.info(f"Admin {admin_user.username} fetched {len(users)} users")
    return users

@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user_by_id(
    user_id: int,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Get specific user by ID (admin only)"""
    cache_key = f"user:{user_id}"
    cached_user = redis_client.get(cache_key)
    if cached_user:
        logger.info(f"Returning cached user {user_id}")
        return json.loads(cached_user)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    redis_client.setex(cache_key, 3600, json.dumps(user.__dict__))
    logger.info(f"Admin {admin_user.username} fetched user {user_id}")
    return user

@app.post("/users", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Create a new user (admin only)"""
    cache_key = f"user:{user_data.username}"
    if redis_client.get(cache_key):
        raise HTTPException(status_code=400, detail="Username already exists (cached)")

    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        redis_client.setex(cache_key, 3600, json.dumps(existing_user.__dict__))
        raise HTTPException(status_code=400, detail="Username already exists")
    
    hashed_password = pwd_context.hash(user_data.password)
    new_user = User(
        username=user_data.username,
        hashed_password=hashed_password,
        role=user_data.role
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    redis_client.setex(f"user:{new_user.id}", 3600, json.dumps(new_user.__dict__))
    redis_client.delete("admin:users:*")  # Invalidate user list cache
    logger.info(f"Admin {admin_user.username} created new user: {new_user.username}")
    return new_user

@app.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    update_data: dict,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Update user information (admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if "username" in update_data:
        existing = db.query(User).filter(
            User.username == update_data["username"], 
            User.id != user_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Username already exists")
        user.username = update_data["username"]
    
    if "role" in update_data:
        if update_data["role"] not in ["user", "admin"]:
            raise HTTPException(status_code=400, detail="Invalid role")
        user.role = update_data["role"]
    
    if "password" in update_data:
        user.hashed_password = pwd_context.hash(update_data["password"])
    
    db.commit()
    db.refresh(user)
    
    redis_client.setex(f"user:{user_id}", 3600, json.dumps(user.__dict__))
    redis_client.delete("admin:users:*")
    logger.info(f"Admin {admin_user.username} updated user: {user.username}")
    return user

@app.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Delete a user (admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.id == admin_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    
    db.query(History).filter(History.user_id == user_id).delete()
    username = user.username
    db.delete(user)
    db.commit()
    
    redis_client.delete(f"user:{user_id}")
    redis_client.delete(f"user:{username}")
    redis_client.delete("admin:users:*")
    logger.info(f"Admin {admin_user.username} deleted user: {username}")
    return {"detail": f"User {username} deleted successfully"}

@app.get("/stats")
async def get_system_stats(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Get system statistics (admin only)"""
    cache_key = "admin:stats"
    cached_stats = redis_client.get(cache_key)
    if cached_stats:
        logger.info(f"Returning cached stats")
        return json.loads(cached_stats)

    total_users = db.query(func.count(User.id)).scalar()
    admin_users = db.query(func.count(User.id)).filter(User.role == "admin").scalar()
    regular_users = total_users - admin_users
    
    total_searches = db.query(func.count(History.id)).filter(History.type == "search").scalar()
    total_images = db.query(func.count(History.id)).filter(History.type == "image").scalar()
    total_activities = total_searches + total_images
    
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_activities = db.query(func.count(History.id)).filter(
        History.created_at >= week_ago
    ).scalar()
    
    most_active = db.query(
        User.username,
        func.count(History.id).label('activity_count')
    ).join(History, User.id == History.user_id)\
    .group_by(User.id, User.username)\
    .order_by(desc(func.count(History.id)))\
    .limit(5).all()
    
    stats = {
        "users": {
            "total": total_users,
            "admin": admin_users,
            "regular": regular_users
        },
        "activities": {
            "total": total_activities,
            "searches": total_searches,
            "images": total_images,
            "recent_week": recent_activities
        },
        "most_active_users": [
            {"username": username, "activity_count": count} 
            for username, count in most_active
        ]
    }
    
    redis_client.setex(cache_key, 3600, json.dumps(stats))
    logger.info(f"Admin {admin_user.username} fetched system stats")
    return stats

@app.get("/users/{user_id}/history", response_model=dict)
async def get_user_history(
    user_id: int,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200)
):
    """Get history for a specific user (admin only)"""
    cache_key = f"user:{user_id}:history:limit{limit}"
    cached_history = redis_client.get(cache_key)
    if cached_history:
        logger.info(f"Returning cached history for user {user_id}")
        return json.loads(cached_history)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    history = db.query(History).filter(
        History.user_id == user_id
    ).order_by(desc(History.created_at)).limit(limit).all()
    
    result = {
        "user": {"id": user.id, "username": user.username, "role": user.role},
        "history": history,
        "total_count": len(history)
    }
    
    redis_client.setex(cache_key, 3600, json.dumps({
        "user": {"id": user.id, "username": user.username, "role": user.role},
        "history": [h.__dict__ for h in history],
        "total_count": len(history)
    }))
    logger.info(f"Admin {admin_user.username} fetched history for user {user_id}")
    return result

@app.put("/users/{user_id}/role")
async def change_user_role(
    user_id: int,
    new_role: dict,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Change user role (admin only)"""
    if "role" not in new_role or new_role["role"] not in ["user", "admin"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'user' or 'admin'")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.id == admin_user.id:
        raise HTTPException(status_code=400, detail="Cannot change your own role")
    
    old_role = user.role
    user.role = new_role["role"]
    db.commit()
    db.refresh(user)
    
    redis_client.setex(f"user:{user_id}", 3600, json.dumps(user.__dict__))
    redis_client.delete("admin:users:*")
    logger.info(f"Admin {admin_user.username} changed user {user.username} role from {old_role} to {user.role}")
    return {"detail": f"User {user.username} role changed from {old_role} to {user.role}"}