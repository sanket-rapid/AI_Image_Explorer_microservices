from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database import get_db
from models import User
import grpc
import sys
import os.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../proto')))
from proto import auth_pb2
from proto import auth_pb2_grpc

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="http://localhost:8001/login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        if token.startswith("Bearer "):
            token = token[len("Bearer "):]
        channel = grpc.insecure_channel('localhost:50051')
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        response = stub.ValidateToken(auth_pb2.ValidateTokenRequest(token=token))
        if not response.valid:
            raise HTTPException(status_code=401, detail=f"Invalid token: {response.error}")
        user = db.query(User).filter(User.username == response.username).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except grpc.RpcError as e:
        raise HTTPException(status_code=401, detail=f"gRPC error: {str(e)}")

def get_admin_user(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user