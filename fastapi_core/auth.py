# fastapi_core/auth.py
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
import os
from datetime import datetime

security = HTTPBearer()

SECRET_KEY = os.environ.get("SECRET_KEY", "your-secret-key")

def verify_jwt(credentials: HTTPAuthorizationCredentials = Security(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        # می‌توانید user_id یا role را از payload استخراج کنید
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="توکن منقضی شده است")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="توکن نامعتبر است")