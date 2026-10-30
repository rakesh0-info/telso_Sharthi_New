from pydantic import BaseModel, Field
from typing import Optional
from enums.contentEnum import content_type
from enums.subjectEnum import subject
from enums.contentEnum import LanguageEnum
from enums.contentEnum import UploadStateEnum

class CreateContentRequest(BaseModel):
    content_type: content_type
    title: str
    language_type: LanguageEnum
    des: Optional[str] = None
    class_name: str = Field(default="XII", alias="class")  # alias if incoming key is 'class'
    subject: subject
    file_upload_state: UploadStateEnum = UploadStateEnum.NOT_START
    

    class Config:
        populate_by_name = True