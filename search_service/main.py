from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from models import History, User
from schemas import SearchRequest, HistoryResponse
from database import get_db
from dependencies import get_current_user
import httpx
import logging
import json
import redis
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")
TAVILY_API_URL = os.getenv("TAVILY_API_URL", "https://api.tavily.com/search")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

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

async def query_tavily(query: str):
    """Query the Tavily API for search results"""
    if not TAVILY_API_KEY:
        raise HTTPException(status_code=500, detail="TAVILY_API_KEY not found in .env file")

    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "basic",
        "max_results": 5,
        "include_answer": True
    }
    logger.info(f"Querying Tavily API with payload: {payload}")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(TAVILY_API_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Tavily API response: {data}")
            return data.get("answer") or data.get("results", [{}])[0].get("content", "No summary available")
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from Tavily API: {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail=f"Search failed: {e.response.text}")
        except Exception as e:
            logger.exception("Exception occurred in query_tavily")
            raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.post("/query", response_model=dict)
async def search_query(
    request: SearchRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Perform a search and save to history"""
    cache_key = f"search:user:{user.id}:query:{request.query}"
    cached_result = redis_client.get(cache_key)
    if cached_result:
        logger.info(f"Returning cached search result for user {user.id}, query: {request.query}")
        return json.loads(cached_result)

    try:
        result = await query_tavily(request.query)
        history = History(
            user_id=user.id,
            type="search",
            query=request.query,
            result=result,
            meta_data='{"source": "official_tavily"}'
        )
        db.add(history)
        db.commit()
        db.refresh(history)

        # Invalidate dashboard cache for this user
        keys = redis_client.keys(f"dashboard:user:{user.id}:*")
        for key in keys:
            redis_client.delete(key)
        
        response = {"result": result}
        redis_client.setex(cache_key, 3600, json.dumps(response))
        logger.info(f"User {user.username} performed search: {request.query}")
        return response
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in search_query: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")