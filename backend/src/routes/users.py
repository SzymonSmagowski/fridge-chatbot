from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from src.core.dependencies import get_auth_service, get_db
from src.schemas.users import UserPublic

router = APIRouter(prefix="/users", tags=["users"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/pairing/start")


@router.get("/me", response_model=UserPublic)
async def get_me(
    token: str = Depends(oauth2_scheme),
    auth_service=Depends(get_auth_service),
    db: Session = Depends(get_db),
):
    user = await auth_service.get_current_user(token, db)
    return user
