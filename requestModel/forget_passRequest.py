from pydantic import EmailStr,BaseModel

class forgetPass(BaseModel):
    email:EmailStr