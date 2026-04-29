from datetime import datetime, timedelta
from uuid import UUID

import jwt
from fastapi import HTTPException, status
from jwt.exceptions import PyJWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from src.core.settings import Settings
from src.models.database import User


class AuthService:
    def __init__(self, settings: Settings):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.device_token_expire_days = settings.DEVICE_TOKEN_EXPIRE_DAYS
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    # Used by the OAuth pair callback to populate the NOT NULL `users.hashed_password`
    # column for the device's shadow user. The shadow user is never logged in via
    # password (legacy /auth/* is gone) — this hash exists only to satisfy the
    # column constraint until the column is dropped in a follow-up migration.
    def get_password_hash(self, password: str) -> str:
        return self.pwd_context.hash(password)

    # --- device JWT (D1) -----------------------------------------------------
    def create_device_token(self, device_id: UUID, family_id: UUID) -> str:
        expires = datetime.utcnow() + timedelta(days=self.device_token_expire_days)
        payload = {
            "sub": str(device_id),
            "family_id": str(family_id),
            "exp": expires,
            "iat": datetime.utcnow(),
            "typ": "device",
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def decode_token(self, token: str) -> dict:
        """Decode + verify any JWT signed with our secret. Raises 401 on failure."""
        try:
            return jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except PyJWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    async def get_current_user(self, token: str, db: Session) -> User:
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except PyJWTError as exc:
            raise credentials_exception from exc

        if payload.get("typ") != "device":
            # Only device JWTs are accepted now — username/password tokens are gone.
            raise credentials_exception

        from src.models import Device

        device_id = payload.get("sub")
        if not device_id:
            raise credentials_exception
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device or not device.shadow_user_id:
            raise credentials_exception
        user = db.query(User).filter(User.id == device.shadow_user_id).first()
        if not user:
            raise credentials_exception
        return user
