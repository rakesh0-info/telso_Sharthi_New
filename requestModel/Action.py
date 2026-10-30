from pydantic import BaseModel, EmailStr

class school_action(BaseModel):
    school_code: str
    action_type: str

class user_Action(BaseModel):
    email: EmailStr
    action_type: str

class contentAdminAction(BaseModel):
    questionSetid:int
    action_type: str