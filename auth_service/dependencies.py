from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database import get_db
from models import User
from dotenv import load_dotenv
import os
import grpc
import sys
import os.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../proto')))
from proto import auth_pb2
from proto import auth_pb2_grpc

# Load environment variables
load_dotenv()
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{AUTH_SERVICE_URL}/login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        # Connect to auth_service gRPC server
        channel = grpc.insecure_channel('localhost:50051')
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        response = stub.ValidateToken(auth_pb2.ValidateTokenRequest(token=token))
        
        if not response.valid:
            raise HTTPException(status_code=401, detail=f"Invalid token: {response.error}")
        
        # Verify user in local database
        user = db.query(User).filter(User.username == response.username).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except grpc.RpcError as e:
        raise HTTPException(status_code=401, detail=f"gRPC error: {str(e)}")