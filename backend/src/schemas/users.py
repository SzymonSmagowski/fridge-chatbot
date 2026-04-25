from pydantic import BaseModel


class UserPublic(BaseModel):
    id: int
    username: str
    email: str | None = None
    is_active: bool

    class Config:
        from_attributes = True
