from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from models import History, User
from schemas import ImageRequest, HistoryResponse
from database import get_db
from dependencies import get_current_user
import mcp
from mcp.client.streamable_http import streamablehttp_client
import logging
import json
import os
from dotenv import load_dotenv
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
    """Generate an image using the Flux MCP API with fallback to mock response"""
    mock_url = f"https://example.com/images/{prompt.replace(' ', '_')}.png"
    if not FLUX_API_KEY:
        logger.warning("FLUX_API_KEY not found in .env file, using mock response")
        logger.info(f"Generated mock image URL: {mock_url}")
        return mock_url, True

    url = f"{FLUX_API_URL}?api_key={FLUX_API_KEY}"
    logger.info(f"Connecting to Flux MCP at {url} with prompt: {prompt}")

    try:
        async with streamablehttp_client(url) as (read_stream, write_stream, _):
            logger.info("streamablehttp_client started")
            async with mcp.ClientSession(read_stream, write_stream) as session:
                logger.info("MCP session created")
                await session.initialize()
                logger.info("Session initialized")
                tools_result = await session.list_tools()
                logger.info(f"Available tools: {[tool.name for tool in tools_result.tools]}")

                if not tools_result.tools:
                    logger.error("No tools available from Flux MCP")
                    logger.info(f"Falling back to mock image URL: {mock_url}")
                    return mock_url, True

                tool_name = "generateImageUrl"
                result = await session.call_tool(
                    name=tool_name,
                    arguments={"prompt": prompt}
                )
                logger.info(f"Response from {tool_name}: {result}")

                if not result or result.isError:
                    logger.error(f"No valid response from {tool_name}: {result.error if result.isError else 'No result'}")
                    logger.info(f"Falling back to mock image URL: {mock_url}")
                    return mock_url, True

                if result.content and len(result.content) > 0 and hasattr(result.content[0], 'text'):
                    json_str = result.content[0].text
                    try:
                        data = json.loads(json_str)
                        image_url = data.get("imageUrl")
                        if not image_url:
                            logger.error(f"No imageUrl in response from {tool_name}: {data}")
                            logger.info(f"Falling back to mock image URL: {mock_url}")
                            return mock_url, True
                        logger.info(f"Generated image URL: {image_url}")
                        return image_url, False
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON response: {str(e)}")
                        logger.info(f"Falling back to mock image URL: {mock_url}")
                        return mock_url, True
                else:
                    logger.error(f"No valid content in response from {tool_name}")
                    logger.info(f"Falling back to mock image URL: {mock_url}")
                    return mock_url, True
    except Exception as e:
        logger.exception(f"Exception occurred in generate_image: {str(e)}")
        logger.info(f"Falling back to mock image URL: {mock_url}")
        return mock_url, True

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
        image_url, is_mock = await generate_image(request.prompt)
        history = History(
            user_id=user.id,
            type="image",
            query=request.prompt,
            result=image_url,
            meta_data=f'{{"source": "flux_imagegen_mcp", "is_mock": {str(is_mock).lower()}}}'
        )
        db.add(history)
        db.commit()
        db.refresh(history)

        # Invalidate dashboard cache for this user
        keys = redis_client.keys(f"dashboard:user:{user.id}:*")
        for key in keys:
            redis_client.delete(key)
        
        result = {
            "image_url": image_url,
            "warning": "Using mock response due to Flux API failure" if is_mock else None
        }
        redis_client.setex(cache_key, 3600, json.dumps(result))
        logger.info(f"User {user.username} generated image for prompt: {request.prompt}")
        return result
    except Exception as e:
        logger.error(f"Error in generate_image_endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Image generation failed: {str(e)}")