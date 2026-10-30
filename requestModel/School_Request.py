from pydantic import BaseModel
from enums.userActivationEnum import activation

class create_schools(BaseModel):
    school_name: str
    school_code: str
    district: str
    region: str
    address: str
    phone: str
    activation_status: activation
    school_admin_email: str | None = None