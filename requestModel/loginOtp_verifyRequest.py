from pydantic import BaseModel,EmailStr

class otp_verify(BaseModel):
    email:EmailStr
    otp_input:str