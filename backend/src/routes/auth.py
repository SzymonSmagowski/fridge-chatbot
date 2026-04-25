"""Legacy /auth/* routes (§5.10).

Retained as machinery for `Thread.user_id` FKs (§4.2). Rate-limited via slowapi
with Redis storage so multiple uvicorn workers share counters.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from src.core.dependencies import get_auth_service, get_db, get_settings
from src.core.rate_limit import get_limiter
from src.models.database import User
from src.schemas.auth import LoginRequest, TokenWithUser, UserCreate

router = APIRouter(prefix="/auth", tags=["auth"])

limiter = get_limiter(get_settings())


@router.post(
    "/register", response_model=TokenWithUser, status_code=status.HTTP_201_CREATED
)
@limiter.limit("3/minute")
async def register(
    request: Request,  # required by slowapi
    payload: UserCreate,
    db: Session = Depends(get_db),
    auth_service=Depends(get_auth_service),
):
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken")

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=auth_service.get_password_hash(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = auth_service.create_access_token(data={"sub": user.username})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user.id, "username": user.username, "email": user.email},
    }


@router.post("/login", response_model=TokenWithUser)
@limiter.limit("5/minute")
async def login(
    request: Request,
    payload: LoginRequest,
    db: Session = Depends(get_db),
    auth_service=Depends(get_auth_service),
):
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not auth_service.verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = auth_service.create_access_token(data={"sub": user.username})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user.id, "username": user.username, "email": user.email},
    }


@router.post("/refresh", response_model=TokenWithUser)
@limiter.limit("10/minute")
async def refresh(
    request: Request,
    payload: LoginRequest,
    db: Session = Depends(get_db),
    auth_service=Depends(get_auth_service),
):
    """Re-issue a token for an already-authenticated username/password pair.

    Implemented as a thin wrapper over the same credential check as login —
    keeping the public surface stable while letting the FE periodically refresh.
    """
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not auth_service.verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = auth_service.create_access_token(data={"sub": user.username})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user.id, "username": user.username, "email": user.email},
    }
