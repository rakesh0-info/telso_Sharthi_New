from datetime import datetime, timedelta, timezone
import time
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Header, Request, status
from sqlalchemy.orm import Session
from jose import jwt, JWTError
import os
from databaseCon import get_db
from jwts.jwt_config import create_access_token
from jwts.token_Verify import verify_token
from mail.sendmail import send_mail
from otp_generate.otp import generate_otp
from requestModel.forget_passRequest import forgetPass
from requestModel.loginRequest import loginRequest
from databaseModel.userModel import User 
from requestModel.reset_pass import reset_pass_Request
from util_validate.password_security import hash_password, verify_password
from requestModel.loginOtp_verifyRequest import otp_verify
from util_validate.pasword_name_validate import passwordCheack
from slowapi import Limiter
from slowapi.util import get_remote_address


limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/public/api/v1", tags=["Public"])

@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    payload: loginRequest,
    db: Session = Depends(get_db),
    bg_tasks: BackgroundTasks = BackgroundTasks()
):
    # FIX: Normalize email input to prevent case-sensitivity login failures
    clean_email = payload.email.strip().lower()
    exist_user = db.query(User).filter(User.email == clean_email).first()
    clear_pass = payload.password.strip()

    if not exist_user or not verify_password(clear_pass, exist_user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    otp = generate_otp()
    expiry_time = datetime.now(timezone.utc) + timedelta(seconds=300)

    exist_user.otp = otp
    exist_user.otp_expiry = expiry_time
    db.commit()
    
    bg_tasks.add_task(send_mail, exist_user.email, otp)

    return {"message": "A verification OTP has been sent to your mail, valid for 5 minutes."}


@router.post("/login_otp_verification")
@limiter.limit("5/minute")
async def otp_verification(request: Request, payload: otp_verify, db: Session = Depends(get_db)):
    clean_email = payload.email.strip().lower()
    clean_otp = payload.otp_input.strip().zfill(6)

    user = db.query(User).filter(User.email == clean_email).first()
    
    if not user or not user.otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP or request."
        )

    user_otp = str(user.otp).strip().zfill(6)
    
    expiry_timestamp = user.otp_expiry.replace(tzinfo=timezone.utc).timestamp() if user.otp_expiry.tzinfo is None else user.otp_expiry.timestamp()
    if clean_otp != user_otp or expiry_timestamp < time.time():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP code."
        )

    user.otp = None
    user.otp_expiry = None
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    access_token = create_access_token({"sub": user.email, "scope": "login_Verification"})
    role_str = user.role.value if hasattr(user.role, "value") else str(user.role)

    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "role": role_str,
        "redirect_url": f"{role_str}/api/v1/dashboard"
    }


@router.post("/forget_Pass")
@limiter.limit("3/minute")
async def forget_pass(
    request: Request,
    payload: forgetPass, 
    db: Session = Depends(get_db), 
    bg_tasks: BackgroundTasks = BackgroundTasks()
):
    clean_email = payload.email.strip().lower()
    exist_user = db.query(User).filter(User.email == clean_email).first()
    
    # Mitigation against email enumeration & secure response
    if not exist_user:
        return {
            "message": "If the email exists in our system, an OTP has been sent for resetting the password."
        }

    otp = generate_otp()
    expiry = datetime.now(timezone.utc) + timedelta(seconds=300)

    exist_user.otp = otp
    exist_user.otp_expiry = expiry
    db.commit()
    db.refresh(exist_user)

    bg_tasks.add_task(send_mail, exist_user.email, otp)

    # FIX: REMOVED reset_pass_token from response body. 
    # Tokens should only be issued AFTER successful OTP verification.
    return {
        "message": "If the email exists in our system, an OTP has been sent for resetting the password."
    }


@router.post("/forget_pass_otp_verification")
@limiter.limit("5/minute")
async def verify_otp_forget_pass(request: Request, payload: otp_verify, db: Session = Depends(get_db)):
    clean_email = payload.email.strip().lower()
    clean_otp = payload.otp_input.strip().zfill(6)
     
    user = db.query(User).filter(User.email == clean_email).first()
         
    if not user or not user.otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP or request."
        )
        
    user_otp = str(user.otp).strip().zfill(6)
    
    expiry_timestamp = user.otp_expiry.replace(tzinfo=timezone.utc).timestamp() if user.otp_expiry.tzinfo is None else user.otp_expiry.timestamp()
    if clean_otp != user_otp or expiry_timestamp < time.time():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP code."
        )
     
    # Clear OTP
    user.otp = None
    user.otp_expiry = None
    db.commit()
    db.refresh(user)

    # FIX: Issue a strict short-lived reset token ONLY after successful OTP verification
    reset_pass_token = create_access_token({"sub": user.email, "scope": "forget_pass_token"}, expires_delta=timedelta(minutes=5))

    return {
        "success": True,
        "reset_pass_token": reset_pass_token,
        "message": "OTP verified successfully. Use the reset token to update your password."
    }


@router.post("/reset_password")
@limiter.limit("5/minute")
async def reset_pass(
    request: Request,
    payload: reset_pass_Request, 
    token: str = Header(..., alias="Authorization"), 
    db: Session = Depends(get_db)
):
    if token.startswith("Bearer "):
        token = token.split(" ")[1]

  
    try:
        payload_data = verify_token(token, db) # Assuming verify_token returns decoded payload or user depending on helper implementation
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    try:
        decoded_payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM", "HS256")])
        if decoded_payload.get("scope") != "forget_pass_token":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token scope for password reset")
        user_email = decoded_payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized Access")

    user = db.query(User).filter(User.email == user_email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    if user.otp is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bad Request: OTP verification required."
        )

    is_verify = passwordCheack(payload.New_Password)
    if not is_verify:
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail="Password must be at least 8 characters and include at least one letter, number, and symbol."
        )

    if payload.New_Password != payload.Confirm_Password:
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail="New password and confirm password do not match."
        )

    hashed_pwd = hash_password(payload.New_Password)
    user.password = hashed_pwd
    db.commit()
    db.refresh(user)

    return {
        "message": "Your password has been reset. You can login now."
    }