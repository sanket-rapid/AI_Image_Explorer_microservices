import grpc
from concurrent import futures
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from fastapi import HTTPException
from database import SessionLocal
from models import User
from dotenv import load_dotenv
import os
import logging
import sys
import os.path
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../proto')))
from proto import auth_pb2
from proto import auth_pb2_grpc

# Load environment variables
load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AuthServicer(auth_pb2_grpc.AuthServiceServicer):
    def ValidateToken(self, request, context):
        try:
            db = SessionLocal()
            payload = jwt.decode(request.token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")
            if not username:
                return auth_pb2.ValidateTokenResponse(
                    valid=False, username="", role="", error="Invalid token payload"
                )
            
            user = db.query(User).filter(User.username == username).first()
            if not user:
                return auth_pb2.ValidateTokenResponse(
                    valid=False, username="", role="", error="User not found"
                )
            
            return auth_pb2.ValidateTokenResponse(
                valid=True, username=user.username, role=user.role, error=""
            )
        except JWTError as e:
            logger.error(f"JWT validation error: {str(e)}")
            return auth_pb2.ValidateTokenResponse(
                valid=False, username="", role="", error=str(e)
            )
        finally:
            db.close()

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    auth_pb2_grpc.add_AuthServiceServicer_to_server(AuthServicer(), server)
    server.add_insecure_port('[::]:50051')
    logger.info("Starting gRPC server on port 50051")
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    serve()