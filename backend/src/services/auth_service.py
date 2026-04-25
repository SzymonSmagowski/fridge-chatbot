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
        self.access_token_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self.device_token_expire_days = settings.DEVICE_TOKEN_EXPIRE_DAYS
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    # TODO(compliance): Pinned bcrypt<5 in pyproject.toml due to passlib's
    # `bcrypt.__about__` probe incompatibility. When moving to passlib 1.8+
    # or replacing with argon2-cffi, the bcrypt pin can be removed.
    def get_password_hash(self, password: str) -> str:
        return self.pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return self.pwd_context.verify(plain_password, hashed_password)

    def create_access_token(self, data: dict) -> str:
        expires = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        payload = {**data, "exp": expires}
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

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

        if payload.get("typ") == "device":
            # Device JWT — resolve the shadow user attached to this device so
            # legacy /threads endpoints continue to work.
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

        username = payload.get("sub")
        if not username:
            raise credentials_exception
        user = db.query(User).filter(User.username == username).first()
        if not user or not user.is_active:
            raise credentials_exception
        return user
