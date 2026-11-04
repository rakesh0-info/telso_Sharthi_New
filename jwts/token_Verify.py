
from fastapi import HTTPException,status,Depends
import os
from dotenv import load_dotenv
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from databaseModel.userModel import User

from databaseCon import get_db
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is missing!")

ALGORITHM = os.getenv(
    "ALGORITHM",
    "HS256"
)

def verify_token(token=str,db:Session=Depends(get_db)):
    cred_exc = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    try:
    
            payload = jwt.decode(
                token,
                SECRET_KEY,
                algorithms=[ALGORITHM]
            )
    
            user_email: str | None = payload.get("sub")
    
            token_type: str | None = payload.get("scope")
    
            # ----------------------------------------------------
            # Missing email
            # ----------------------------------------------------
    
            if user_email is None:
                raise cred_exc
    
          # ----------------------------------------------------
            # Reject refresh token
            # ----------------------------------------------------
    
            if token_type =="login_Verification" or token_type=="forget_pass_token" or token_type=="access":
                #   sjb
                print ("ok brother")
            else:
                  raise cred_exc
    
    except JWTError:
    
            
    
            raise cred_exc
    
        # ========================================================
        # FIND USER
        # ========================================================
    
    user = (
            db.query(User)
            .filter(
                User.email == user_email
            )
            .first()
        )
    
    if not user:
    
            
    
            raise cred_exc
    
    return user
