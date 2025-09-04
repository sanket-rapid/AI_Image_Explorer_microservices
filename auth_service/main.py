from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from models import User
from dependencies import get_current_user
from schemas import UserCreate, UserResponse, Token
from database import get_db
from passlib.context import CryptContext
from jose import jwt, JWTError
from dotenv import load_dotenv
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import redis
import os

# Load environment variables
load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY not found in .env file")
ALGORITHM = "HS256"
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")

# Initialize Redis
redis_client = redis.Redis(host=REDIS_HOST, port=int(REDIS_PORT), decode_responses=True)

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

def create_access_token(data: dict, expires_delta: timedelta = timedelta(minutes=30)):
    to_encode = data.copy()
    ist = ZoneInfo("Asia/Kolkata")
    expire = datetime.now(ist) + expires_delta
    to_encode.update({"exp": int(expire.timestamp())})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

@app.post("/register", response_model=Token)
async def register(user: UserCreate, db: Session = Depends(get_db)):
    # Check Redis cache for user
    cache_key = f"user:{user.username}"
    if redis_client.get(cache_key):
        raise HTTPException(status_code=400, detail="Username already exists (cached)")

    # Check database
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        redis_client.setex(cache_key, 3600, "exists")  # Cache for 1 hour
        raise HTTPException(status_code=400, detail="Username already exists")

    # Create new user
    hashed_password = pwd_context.hash(user.password)
    db_user = User(username=user.username, hashed_password=hashed_password, role=user.role)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # Generate and cache token
    token = create_access_token({"sub": user.username, "role": user.role})
    redis_client.setex(f"token:{user.username}", 3600, token)  # Cache token for 1 hour
    return {"access_token": token, "token_type": "bearer"}

@app.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Check Redis cache for token
    cache_key = f"token:{form_data.username}"
    cached_token = redis_client.get(cache_key)
    if cached_token:
        try:
            payload = jwt.decode(cached_token, SECRET_KEY, algorithms=[ALGORITHM])
            exp = payload.get("exp")
            if exp is None:
                raise HTTPException(status_code=401, detail="Token missing expiration")
            if exp > int(datetime.utcnow().timestamp()):
                return {"access_token": cached_token, "token_type": "bearer"}
        except JWTError:
            pass  # Token invalid or expired, proceed to database

    # Check database
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not pwd_context.verify(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Generate and cache token
    token = create_access_token({"sub": user.username, "role": user.role})
    redis_client.setex(cache_key, 3600, token)  # Cache for 1 hour
    return {"access_token": token, "token_type": "bearer"}

@app.get("/validate", response_model=UserResponse)
async def validate_token(current_user: User = Depends(get_current_user)):
    return current_user