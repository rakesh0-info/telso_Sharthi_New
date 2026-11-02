from typing import Optional
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from enums import ContentTypeEnum


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContentCreate(RequestModel):
    content_type: ContentTypeEnum
    title: str = Field(min_length=2, max_length=255)
    content_code: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, max_length=1000)
    
    school_id: int = Field(gt=0)
    class_id: int = Field(gt=0)
    subject_id: int = Field(gt=0)
    chapter_id: Optional[int] = Field(default=None, gt=0)
    topic_id: Optional[int] = Field(default=None, gt=0)
    
    keywords: Optional[str] = Field(default=None, max_length=500)
    
    # Language file paths / URLs or upload indicators
    english_file_url: Optional[str] = Field(default=None, max_length=500)
    manipuri_file_url: Optional[str] = Field(default=None, max_length=500)

    @field_validator("title", "content_code", "description", "keywords", "english_file_url", "manipuri_file_url", mode="before")
    @classmethod
    def strip_text(cls, value):
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned if cleaned else None

    @model_validator(mode="after")
    def validate_language_files(self):
        """Edge case handler: Ensure at least one language version file is provided."""
        if not self.english_file_url and not self.manipuri_file_url:
            raise ValueError("At least one language file (English or Manipuri) must be uploaded.")
        return self

    @model_validator(mode="after")
    def validate_hierarchy(self):
        """Ensure logical hierarchy correlation if topic is given."""
        if self.topic_id is not None and self.chapter_id is None:
            raise ValueError("chapter_id is required when topic_id is provided.")
        return self