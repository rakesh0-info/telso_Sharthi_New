from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from starlette import status

from databaseCon import get_db
from databaseModel.userModel import User
from enums import ActivationStatus
from jwts.jwt_config import ALGORITHM, SECRET_KEY

load_dotenv()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/public/api/v1/login")


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        subject = payload.get("sub")
        token_type = payload.get("type")
        expiration = payload.get("exp")

        # Require an access token with a subject and exp. jwt.decode validates exp
        # when present; requiring it here prevents non-expiring JWTs.
        if (
            not isinstance(subject, str)
            or not subject.strip()
            or token_type != "access"
            or expiration is None
        ):
            raise _unauthorized()

    except (JWTError, TypeError, ValueError):
        raise _unauthorized()

    user = db.query(User).filter(User.email == subject.strip().lower()).first()
    if user is None:
        raise _unauthorized()
    return user


def get_authenticated_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    activation = current_user.activation_status
    activation_value = activation.value if hasattr(activation, "value") else str(activation)

    if activation_value.lower() != ActivationStatus.ACTIVE.value.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive. Contact the administrator.",
        )
    return current_user


def require_roles(*allowed_roles: Any):
    if not allowed_roles:
        raise ValueError("require_roles must receive at least one allowed role.")

    allowed_values = {
        role.value if hasattr(role, "value") else str(role)
        for role in allowed_roles
    }

    def role_checker(
        user: User = Depends(get_authenticated_active_user),
    ) -> User:
        user_role = user.role.value if hasattr(user.role, "value") else str(user.role)
        if user_role not in allowed_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access forbidden: insufficient permissions.",
            )
        return user

    return role_checker
