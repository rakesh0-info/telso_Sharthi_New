from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
import os

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload
from jose import jwt, JWTError

from databaseCon import get_db
from databaseModel.userModel import User
from databaseModel.schoolModel import School
from databaseModel.classModel import ClassModel, ClassSection
from databaseModel.teacherModel import Teacher
from databaseModel.studentModel import Student
from databaseModel.subjectModel import Subject
from databaseModel.teacherLessonModel import TeacherLessonContent, TeacherLessonShare
from databaseModel.questionSetModel import QuestionSet, QuestionSetItem
from databaseModel.teacherQuizModel import TeacherQuizPublication
from enums import RoleEnum, ActivationStatus, GenderEnum

router = APIRouter(prefix="/api/student", tags=["Student Portal"])
security = HTTPBearer()

# JWT Configuration (Ensure these match your application's environment configuration)
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secure-jwt-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24


# ---------------------------------------------------------------------------
# Shared validation helpers & Request Models
# ---------------------------------------------------------------------------

class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("This field cannot be blank.")
    return cleaned


class StudentLoginRequest(RequestModel):
    parents_ph_no: str = Field(pattern=r"^\d{10}$")
    student_email: Optional[EmailStr] = None  # Optional disambiguation if multiple children share a parent phone number

    @field_validator("parents_ph_no")
    @classmethod
    def clean_phone(cls, value: str) -> str:
        return value.strip()


def _create_student_token(student_id: int, school_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": str(student_id),
        "school_id": school_id,
        "role": "STUDENT",
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_student(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)) -> Student:
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate student credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        student_id_str: str = payload.get("sub")
        role: str = payload.get("role")
        if student_id_str is None or role != "STUDENT":
            raise credentials_exception
        student_id = int(student_id_str)
    except (JWTError, ValueError):
        raise credentials_exception

    student = db.query(Student).options(
        selectinload(Student.school),
        selectinload(Student.class_obj),
        selectinload(Student.section_obj),
    ).filter(Student.id == student_id).first()

    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found.")
    return student


# ---------------------------------------------------------------------------
# 1. Student Login (Credential: Parent's Phone Number)
# ---------------------------------------------------------------------------

@router.post("/login", status_code=status.HTTP_200_OK)
def student_login(data: StudentLoginRequest, db: Session = Depends(get_db)):
    query = db.query(Student).filter(Student.parents_ph_no == data.parents_ph_no)
    
    students = query.all()
    if not students:
        raise HTTPException(status_code=401, detail="Invalid parent phone number or student record not found.")

    # Edge Case: Multiple children associated with the same parent phone number
    if len(students) > 1:
        if not data.student_email:
            raise HTTPException(
                status_code=400,
                detail="Multiple students found under this parent phone number. Please provide 'student_email' to authenticate."
            )
        student = next((s for s in students if s.email and s.email.lower() == data.student_email.lower()), None)
        if not student:
            raise HTTPException(status_code=401, detail="No student matching this email found under the given parent phone number.")
    else:
        student = students[0]

    # Verify school status if school relation exists
    if student.school and hasattr(student.school, "activation"):
        status_val = student.school.activation.value if hasattr(student.school.activation, "value") else student.school.activation
        if status_val != ActivationStatus.ACTIVE.value and status_val != ActivationStatus.ACTIVE:
            raise HTTPException(status_code=403, detail="Associated school account is inactive.")

    token = _create_student_token(student.id, student.school_id)
    return {
        "message": "Login successful.",
        "access_token": token,
        "token_type": "bearer",
        "student_id": student.id,
        "student_name": student.name,
    }


# ---------------------------------------------------------------------------
# 2. Get Class, Sections, Subjects, and Teachers
# ---------------------------------------------------------------------------

@router.get("/get-class", status_code=status.HTTP_200_OK)
def get_student_class_details(
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    if not current_student.class_id:
        raise HTTPException(status_code=404, detail="Student is not assigned to any class yet.")

    class_obj = db.query(ClassModel).options(
        selectinload(ClassModel.sections),
        selectinload(ClassModel.subjects).selectinload(Subject.chapters),
        selectinload(ClassModel.teachers).selectinload(Teacher.user),
    ).filter(ClassModel.id == current_student.class_id).first()

    if not class_obj:
        raise HTTPException(status_code=404, detail="Assigned class record not found.")

    # Get the specific section the student belongs to
    student_section = current_student.section_obj
    section_data = {
        "section_id": student_section.id,
        "section_name": student_section.section_name,
    } if student_section else None

    # Format teachers assigned to this class
    class_teachers = [{
        "teacher_id": t.id,
        "name": t.user.name if t.user else None,
        "email": t.user.email if t.user else None,
        "qualification": t.qualification,
    } for t in class_obj.teachers]

    # Map class teachers and total chapters count to each subject
    subjects_list = [{
        "subject_id": sub.id,
        "subject_name": sub.name,
        "total_chapters": len(sub.chapters),
        "teachers": class_teachers
    } for sub in class_obj.subjects]

    return {
        "class_id": class_obj.id,
        "class_name": class_obj.class_name,
        "grade_level": class_obj.grade_level,
        "section": section_data,
        "subjects": subjects_list,
    }
# ---------------------------------------------------------------------------
# 3. Student Dashboard (Class, School, and Personal Details)
# ---------------------------------------------------------------------------

@router.get("/dashboard", status_code=status.HTTP_200_OK)
def get_student_dashboard(
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    school = current_student.school
    class_obj = current_student.class_obj
    section_obj = current_student.section_obj

    return {
        "student_profile": {
            "student_id": current_student.id,
            "name": current_student.name,
            "email": current_student.email,
            "gender": current_student.gender.value if hasattr(current_student.gender, "value") else current_student.gender,
            "dob": current_student.dob,
            "phone_number": current_student.phone_number,
        },
        "school_details": {
            "school_id": school.id if school else None,
            "school_name": school.name if school else None,
            "school_code": school.school_code if school else None,
            "district": school.distc if school and hasattr(school, "distc") else None,
            "state": school.state if school else None,
            "phone": school.school_ph_no if school else None,
        },
        "academic_placement": {
            "class_id": class_obj.id if class_obj else None,
            "class_name": class_obj.class_name if class_obj else None,
            "grade_level": class_obj.grade_level if class_obj else None,
            "section_id": section_obj.id if section_obj else None,
            "section_name": section_obj.section_name if section_obj else None,
        },
        "parent_guardian_info": {
            "parents_name": current_student.parents_name,
            "parents_ph_no": current_student.parents_ph_no,
            "parents_email": current_student.parents_email,
        }
    }


@router.get("/lessons", status_code=status.HTTP_200_OK)
def get_shared_lessons(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    school = current_student.school
    status_value = (
        school.activation.value
        if school and hasattr(school.activation, "value")
        else (school.activation if school else None)
    )
    if school is None or status_value != ActivationStatus.ACTIVE.value:
        raise HTTPException(
            status_code=403,
            detail="Lesson access is unavailable for an inactive or missing school.",
        )
    if current_student.class_id is None or current_student.section_id is None:
        return []

    lessons = (
        db.query(TeacherLessonContent)
        .join(
            TeacherLessonShare,
            TeacherLessonShare.lesson_id == TeacherLessonContent.id,
        )
        .options(
            selectinload(TeacherLessonContent.class_obj),
            selectinload(TeacherLessonContent.section),
            selectinload(TeacherLessonContent.subject),
            selectinload(TeacherLessonContent.chapter),
            selectinload(TeacherLessonContent.topic),
        )
        .filter(
            TeacherLessonContent.school_id == current_student.school_id,
            TeacherLessonContent.class_id == current_student.class_id,
            TeacherLessonShare.section_id == current_student.section_id,
            TeacherLessonShare.revoked_at.is_(None),
            or_(
                TeacherLessonShare.student_id.is_(None),
                TeacherLessonShare.student_id == current_student.id,
            ),
        )
        .distinct()
        .order_by(TeacherLessonContent.updated_at.desc(), TeacherLessonContent.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        {
            "lesson_id": lesson.id,
            "name": lesson.name,
            "content": lesson.content,
            "content_type": lesson.content_type,
            "status": "shared",
            "school_id": lesson.school_id,
            "class_id": lesson.class_id,
            "class_name": lesson.class_obj.class_name if lesson.class_obj else None,
            "section_id": current_student.section_id,
            "section_name": (
                current_student.section_obj.section_name
                if current_student.section_obj
                else None
            ),
            "subject_id": lesson.subject_id,
            "subject_name": lesson.subject.name if lesson.subject else None,
            "chapter_id": lesson.chapter_id,
            "chapter_name": lesson.chapter.chapter_name if lesson.chapter else None,
            "topic_id": lesson.topic_id,
            "topic_name": lesson.topic.topic_name if lesson.topic else None,
            "created_at": lesson.created_at,
            "updated_at": lesson.updated_at,
        }
        for lesson in lessons
    ]


def _quiz_is_active(question_set: QuestionSet, now: datetime) -> bool:
    if question_set.scheduled_at is None:
        return False
    scheduled_at = question_set.scheduled_at
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    else:
        scheduled_at = scheduled_at.astimezone(timezone.utc)
    return scheduled_at <= now < scheduled_at + timedelta(minutes=question_set.duration_minutes)


def _quiz_is_listable(question_set: QuestionSet, now: datetime) -> bool:
    if question_set.scheduled_at is None:
        return False
    scheduled_at = question_set.scheduled_at
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    else:
        scheduled_at = scheduled_at.astimezone(timezone.utc)
    return scheduled_at + timedelta(minutes=question_set.duration_minutes) > now


def _student_quiz_query(db: Session, current_student: Student):
    return (
        db.query(QuestionSet)
        .join(
            TeacherQuizPublication,
            TeacherQuizPublication.question_set_id == QuestionSet.id,
        )
        .join(
            ClassSection,
            ClassSection.id == TeacherQuizPublication.section_id,
        )
        .filter(
            TeacherQuizPublication.section_id == current_student.section_id,
            TeacherQuizPublication.class_id == current_student.class_id,
            ClassSection.class_id == QuestionSet.class_id,
            TeacherQuizPublication.class_id == QuestionSet.class_id,
            QuestionSet.school_id == current_student.school_id,
            QuestionSet.class_id == current_student.class_id,
            QuestionSet.section_id == current_student.section_id,
        )
    )


@router.get("/quizzes", status_code=status.HTTP_200_OK)
def get_available_student_quizzes(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    school = current_student.school
    school_status = (
        school.activation.value
        if school and hasattr(school.activation, "value")
        else (school.activation if school else None)
    )
    if school is None or school_status != ActivationStatus.ACTIVE.value:
        raise HTTPException(status_code=403, detail="Quiz access is unavailable for an inactive or missing school.")
    if current_student.class_id is None or current_student.section_id is None:
        return []
    if (
        current_student.section_obj is None
        or current_student.section_obj.class_id != current_student.class_id
    ):
        return []

    now = datetime.now(timezone.utc)
    question_sets = (
        _student_quiz_query(db, current_student)
        .filter(QuestionSet.scheduled_at.isnot(None))
        .order_by(QuestionSet.scheduled_at, QuestionSet.id)
        .all()
    )
    listable_question_sets = [
        question_set
        for question_set in question_sets
        if _quiz_is_listable(question_set, now)
    ]
    return [
        {
            "question_set_id": question_set.id,
            "name": question_set.name,
            "class_id": question_set.class_id,
            "subject_id": question_set.subject_id,
            "chapter_id": question_set.chapter_id,
            "topic_id": question_set.topic_id,
            "question_count": question_set.question_count,
            "scheduled_at": question_set.scheduled_at,
            "duration_minutes": question_set.duration_minutes,
            "status": "active" if _quiz_is_active(question_set, now) else "upcoming",
        }
        for question_set in listable_question_sets[skip : skip + limit]
    ]


@router.get("/quizzes/{question_set_id}", status_code=status.HTTP_200_OK)
def get_active_student_quiz(
    question_set_id: int = Path(gt=0),
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    school = current_student.school
    school_status = (
        school.activation.value
        if school and hasattr(school.activation, "value")
        else (school.activation if school else None)
    )
    if school is None or school_status != ActivationStatus.ACTIVE.value:
        raise HTTPException(status_code=403, detail="Quiz access is unavailable for an inactive or missing school.")
    if current_student.class_id is None or current_student.section_id is None:
        raise HTTPException(status_code=404, detail="Quiz not found.b")
    if (
        current_student.section_obj is None
        or current_student.section_obj.class_id != current_student.class_id
    ):
        raise HTTPException(status_code=404, detail="Quiz not found.a")

    question_set = (
        _student_quiz_query(db, current_student)
        .options(selectinload(QuestionSet.items).selectinload(QuestionSetItem.question))
        .filter(QuestionSet.id == question_set_id)
        .first()
    )
    if question_set is None or not _quiz_is_active(question_set, datetime.now(timezone.utc)):
        raise HTTPException(status_code=404, detail="Quiz is not available.s")
    return {
        "question_set_id": question_set.id,
        "name": question_set.name,
        "class_id": question_set.class_id,
        "section_id": current_student.section_id,
        "scheduled_at": question_set.scheduled_at,
        "duration_minutes": question_set.duration_minutes,
        "questions": [
            {
                "question_id": item.question.id,
                "position": item.position,
                "question_text": item.question.question_text,
                "options": item.question.options or [],
                "question_type": item.question.question_type,
                "question_level": item.question.question_level,
            }
            for item in question_set.items
        ],
    }