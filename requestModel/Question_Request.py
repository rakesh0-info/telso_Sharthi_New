from pydantic import BaseModel, Field
from typing import List, Optional
from enums.contentEnum import LanguageEnum
from enums.subjectEnum import subject as SubjectEnum
from enums.questionEnum import QuestionTypeEnum, DifficultyEnum, QuestionSetStatusEnum

class GenerateQuestionRequest(BaseModel):
    set_name: str = Field(..., min_length=2, max_length=150, description="Name of the question set")
    class_name: str = Field(default="XII", description="Class name, default is XII")
    subject: SubjectEnum = Field(..., description="Subject enum")
    chapter: str = Field(..., min_length=1, description="Chapter name")
    topic: Optional[str] = Field(None, description="Optional topic name")
    language_type: LanguageEnum = Field(..., description="Language for question generation")
    num_questions: int = Field(default=25, ge=1, le=100, description="Number of questions to generate")
    question_types: List[QuestionTypeEnum] = Field(..., description="List of allowed question types")
    difficulty_levels: List[DifficultyEnum] = Field(..., description="Allowed difficulty levels")
    document_id: int = Field(..., description="ID of the uploaded reference document")
    include_explanations: bool = Field(default=True)
    include_source_reference: bool = Field(default=True)
    # status: QuestionSetStatusEnum = Field(default=QuestionSetStatusEnum.DRAFT)