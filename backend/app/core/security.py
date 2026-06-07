
from datetime import datetime, timedelta, timezone

from typing import Any

import bcrypt

from jose import JWTError, jwt

from app.core.config import settings

def hash_password(plain_password: str) -> str:

    return bcrypt.hashpw(plain_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:

    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def _create_token(data: dict[str, Any], expires_delta: timedelta, token_type: str) -> str:

    payload = data.copy()

    now = datetime.now(timezone.utc)

    payload.update({"iat": now, "exp": now + expires_delta, "type": token_type})

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def create_access_token(user_id: int) -> str:

    return _create_token({"sub": str(user_id)}, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES), "access")

def create_refresh_token(user_id: int) -> str:

    return _create_token({"sub": str(user_id)}, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS), "refresh")

def decode_token(token: str, expected_type: str = "access") -> dict[str, Any]:

    try:

        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

    except JWTError as e:

        raise ValueError(f"Invalid token: {e}")

    if payload.get("type") != expected_type:

        raise ValueError(f"Expected {expected_type} token, got {payload.get('type')}")

    return payload

def get_user_id_from_token(token: str, expected_type: str = "access") -> int:

    payload = decode_token(token, expected_type)

    user_id = payload.get("sub")

    if user_id is None:

        raise ValueError("Token missing 'sub' claim")

    return int(user_id)

