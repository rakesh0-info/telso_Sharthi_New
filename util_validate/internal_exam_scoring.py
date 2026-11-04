from __future__ import annotations

QUESTION_MARKS = {
    "mcq": 1,
    "true_false": 1,
    "fill_in_the_blanks": 1,
    "long_answer": 3,
}


def normalize_exam_answer(value: str) -> str:
    return " ".join(value.casefold().split())


def grade_exam_answer(question_type: str, submitted: str, correct: str) -> tuple[int | None, bool | None]:
    if question_type == "long_answer":
        return None, None
    if question_type not in QUESTION_MARKS:
        raise ValueError(f"Unsupported internal exam question type: {question_type}")
    is_correct = normalize_exam_answer(submitted) == normalize_exam_answer(correct)
    return (QUESTION_MARKS[question_type] if is_correct else 0), is_correct


def is_supported_exam_question_type(question_type: str) -> bool:
    return question_type in QUESTION_MARKS
