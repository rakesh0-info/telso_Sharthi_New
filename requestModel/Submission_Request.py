from pydantic import BaseModel, Field, ConfigDict


class AnswerSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    question_id: int = Field(gt=0)
    user_answer: str = Field(max_length=10000)


class SubmitAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    question_set_id: int = Field(gt=0)

    answers: list[AnswerSubmission] = Field(
        min_length=1,
        max_length=500
    )