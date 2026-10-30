from pydantic import BaseModel, EmailStr
from enums.roleEnum import Role
from enums.userActivationEnum import activation

class create_users(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone: str
    role: Role
    password:str
    activation_status: activation

class AssignAchoolAdmin(BaseModel):
    email: EmailStr
    school_code: str