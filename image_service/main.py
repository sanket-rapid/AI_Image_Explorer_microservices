from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from models import History, User
from schemas import ImageRequest, HistoryResponse
from database import get_db
from dependencies import get_current_user
import logging
import json
import requests
from dotenv import load_dotenv
import os
import redis

# Load environment variables
load_dotenv()
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")
FLUX_API_URL = os.getenv("FLUX_API_URL", "https://server.smithery.ai/@falahgs/flux-imagegen-mcp-server/mcp")
FLUX_API_KEY = os.getenv("FLUX_API_KEY")

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

async def generate_image(prompt: str):
    """Mock image generation function (replace with actual Flux API call)"""
    if not FLUX_API_KEY:
        raise HTTPException(status_code=500, detail="FLUX_API_KEY not found in .env file")

    url = f"{FLUX_API_URL}?api_key={FLUX_API_KEY}"
    logger.info(f"Connecting to Flux API at {url}")

    try:
        # Mock response (replace with actual HTTP request to Flux API)
        # Example: response = requests.post(url, json={"prompt": prompt})
        # data = response.json()
        # image_url = data.get("imageUrl")
        image_url = f"https://example.com/images/{prompt.replace(' ', '_')}.png"  # Mock URL
        logger.info(f"Generated image URL: {image_url}")
        return image_url
    except Exception as e:
        logger.exception("Exception occurred in generate_image")
        raise HTTPException(status_code=500, detail=f"Image generation failed: {str(e)}")

@app.post("/generate", response_model=dict)
async def generate_image_endpoint(
    request: ImageRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate an image and save to history"""
    cache_key = f"image:user:{user.id}:prompt:{request.prompt}"
    cached_result = redis_client.get(cache_key)
    if cached_result:
        logger.info(f"Returning cached image for user {user.id}, prompt: {request.prompt}")
        return json.loads(cached_result)

    try:
        image_url = await generate_image(request.prompt)
        history = History(
            user_id=user.id,
            type="image",
            query=request.prompt,
            result=image_url,
            meta_data='{"source": "flux_imagegen"}'
        )
        db.add(history)
        db.commit()
        db.refresh(history)
        
        result = {"image_url": image_url}
        redis_client.setex(cache_key, 3600, json.dumps(result))
        logger.info(f"User {user.username} generated image for prompt: {request.prompt}")
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in generate_image_endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Image generation failed: {str(e)}")