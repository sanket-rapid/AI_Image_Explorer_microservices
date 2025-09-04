from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import jwt, JWTError
import httpx
import os
from dotenv import load_dotenv
from dependencies import get_current_user, User
import redis
import logging
from typing import Optional

load_dotenv()
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL")
DASHBOARD_SERVICE_URL = os.getenv("DASHBOARD_SERVICE_URL")
IMAGE_SERVICE_URL = os.getenv("IMAGE_SERVICE_URL")
SEARCH_SERVICE_URL = os.getenv("SEARCH_SERVICE_URL")

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

# Helper function to forward requests
async def forward_request(url: str, method: str, headers: dict = None, data: dict = None):
    async with httpx.AsyncClient() as client:
        try:
            if method.upper() == "GET":
                response = await client.get(url, headers=headers, params=data)
            elif method.upper() == "POST":
                response = await client.post(url, headers=headers, json=data)
            elif method.upper() == "PUT":
                response = await client.put(url, headers=headers, json=data)
            elif method.upper() == "DELETE":
                response = await client.delete(url, headers=headers)
            else:
                raise HTTPException(status_code=405, detail="Method not allowed")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error forwarding request to {url}: {str(e)}")
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except Exception as e:
            logger.error(f"Error forwarding request to {url}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# Auth Service Routes
@app.post("/auth/register")
async def register(data: dict):
    return await forward_request(f"{AUTH_SERVICE_URL}/register", "POST", data=data)

@app.post("/auth/login")
async def login(data: dict):
    return await forward_request(f"{AUTH_SERVICE_URL}/login", "POST", data=data)

@app.get("/auth/validate")
async def validate(user: User = Depends(get_current_user)):
    headers = {"Authorization": f"Bearer {jwt.encode({'sub': user.username, 'role': user.role, 'id': user.id}, os.getenv('JWT_SECRET_KEY'), algorithm=os.getenv('JWT_ALGORITHM'))}"}
    return await forward_request(f"{AUTH_SERVICE_URL}/validate", "GET", headers=headers)

# Dashboard Service Routes
@app.get("/dashboard")
async def get_dashboard(
    user: User = Depends(get_current_user),
    type: Optional[str] = None,
    keyword: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None
):
    headers = {"Authorization": f"Bearer {jwt.encode({'sub': user.username, 'role': user.role, 'id': user.id}, os.getenv('JWT_SECRET_KEY'), algorithm=os.getenv('JWT_ALGORITHM'))}"}
    params = {"type": type, "keyword": keyword, "date_start": date_start, "date_end": date_end}
    return await forward_request(f"{DASHBOARD_SERVICE_URL}/", "GET", headers=headers, data=params)

@app.put("/dashboard/{id}")
async def update_dashboard(id: int, data: dict, user: User = Depends(get_current_user)):
    headers = {"Authorization": f"Bearer {jwt.encode({'sub': user.username, 'role': user.role, 'id': user.id}, os.getenv('JWT_SECRET_KEY'), algorithm=os.getenv('JWT_ALGORITHM'))}"}
    return await forward_request(f"{DASHBOARD_SERVICE_URL}/dashboard/{id}", "PUT", headers=headers, data=data)

@app.delete("/dashboard/{id}")
async def delete_dashboard(id: int, user: User = Depends(get_current_user)):
    headers = {"Authorization": f"Bearer {jwt.encode({'sub': user.username, 'role': user.role, 'id': user.id}, os.getenv('JWT_SECRET_KEY'), algorithm=os.getenv('JWT_ALGORITHM'))}"}
    return await forward_request(f"{DASHBOARD_SERVICE_URL}/dashboard/{id}", "DELETE", headers=headers)

# Image Service Routes
@app.post("/image/generate")
async def generate_image(data: dict, user: User = Depends(get_current_user)):
    headers = {"Authorization": f"Bearer {jwt.encode({'sub': user.username, 'role': user.role, 'id': user.id}, os.getenv('JWT_SECRET_KEY'), algorithm=os.getenv('JWT_ALGORITHM'))}"}
    return await forward_request(f"{IMAGE_SERVICE_URL}/generate", "POST", headers=headers, data=data)

# Search Service Routes
@app.post("/search/query")
async def search_query(data: dict, user: User = Depends(get_current_user)):
    headers = {"Authorization": f"Bearer {jwt.encode({'sub': user.username, 'role': user.role, 'id': user.id}, os.getenv('JWT_SECRET_KEY'), algorithm=os.getenv('JWT_ALGORITHM'))}"}
    return await forward_request(f"{SEARCH_SERVICE_URL}/query", "POST", headers=headers, data=data)