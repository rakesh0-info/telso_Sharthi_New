from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Optional
import os
from zoneinfo import ZoneInfo

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from sqlalchemy import func, literal, or_, union_all
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload
from jose import jwt, JWTError

from databaseCon import get_db
from controller.publicController import limiter
from databaseModel.userModel import User
from databaseModel.schoolModel import School
from databaseModel.classModel import ClassModel, ClassSection, school_classes
from databaseModel.teacherModel import Teacher
from databaseModel.studentModel import Student
from databaseModel.subjectModel import Subject
from databaseModel.teacherLessonModel import TeacherLessonContent, TeacherLessonShare
from databaseModel.teacherChapterNoteModel import (
    TeacherChapterNote,
    TeacherChapterNoteShare,
)
from databaseModel.teacherTeachingNoteModel import (
    TeacherTeachingNote,
    TeacherTeachingNoteShare,
)
from databaseModel.teacherHomeworkModel import TeacherHomework, TeacherHomeworkSubmission
from databaseModel.questionSetModel import QuestionSet, QuestionSetItem
from databaseModel.teacherQuizModel import TeacherQuizPublication
from databaseModel.internalExamModel import (
    InternalExam,
    InternalExamAttempt,
    InternalExamResult,
    StudentExamResponse,
)
from enums import RoleEnum, ActivationStatus, GenderEnum
from util_validate.homework_file_security import (
    FILE_MEDIA_TYPES,
    remove_homework_upload,
    resolve_homework_upload,
    save_homework_upload,
)
from util_validate.internal_exam_status import refresh_internal_exam_status
from util_validate.internal_exam_scoring import (
    QUESTION_MARKS,
    grade_exam_answer,
    is_supported_exam_question_type,
)

from slowapi import Limiter
from slowapi.util import get_remote_address


limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/api/student", tags=["Student Portal"])
security = HTTPBearer()
logger = logging.getLogger(__name__)

# JWT Configuration (Ensure these match your application's environment configuration)
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is missing!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 7
MAX_HOMEWORK_ANSWER_LENGTH = 10_000
HOMEWORK_TIMEZONE = ZoneInfo("Asia/Kolkata")


# ---------------------------------------------------------------------------
# Shared validation helpers & Request Models
# ---------------------------------------------------------------------------

class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SubmitExamAnswer(RequestModel):
    question_id: int = Field(gt=0)
    answer: str = Field(max_length=10_000)

    @field_validator("answer")
    @classmethod
    def trim_answer(cls, value: str) -> str:
        return value.strip()


class SubmitInternalExamRequest(RequestModel):
    answers: list[SubmitExamAnswer] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def reject_duplicate_question_answers(self):
        question_ids = [answer.question_id for answer in self.answers]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("An exam question can only be answered once.")
        return self


def _clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("This field cannot be blank.")
    return cleaned


class StudentLoginRequest(RequestModel):
    parents_ph_no: str = Field(pattern=r"^\d{10}$")
    student_email:EmailStr   # Optional disambiguation if multiple children share a parent phone number

    @field_validator("parents_ph_no")
    @classmethod
    def clean_phone(cls, value: str) -> str:
        return value.strip()


def _create_student_token(student_id: int, school_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(student_id),
        "school_id": school_id,
        "role": "STUDENT",
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def is_deactivate_School(db: Session, school_id: int) -> bool:
    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        return True  # School does not exist, treat as deactivated
    status_value = (
        school.activation.value
        if hasattr(school.activation, "value")
        else (school.activation if school else None)
    )
    return status_value != ActivationStatus.ACTIVE.value


def get_current_student(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)) -> Student:
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate student credentials or the school is not activated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        student_id_str = payload.get("sub")
        role: str = payload.get("role")
        token_school_id = payload.get("school_id")
        if (
            not isinstance(student_id_str, str)
            or not student_id_str.isdecimal()
            or role != "STUDENT"
            or type(token_school_id) is not int
            or token_school_id <= 0
            or is_deactivate_School(db, token_school_id)
        ):
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
    if student.school_id != token_school_id:
        raise credentials_exception
    return student


# ---------------------------------------------------------------------------
# 1. Student Login (Credential: Parent's Phone Number)
# ---------------------------------------------------------------------------

@router.post("/login", status_code=status.HTTP_200_OK)
@limiter.limit("3/minute")
def student_login(request: Request,data: StudentLoginRequest, db: Session = Depends(get_db)):
    query = db.query(Student).filter(Student.parents_ph_no == data.parents_ph_no,Student.email== data.student_email
                                     )
    
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

    # Otp send in student email
    # verify otp

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


def _validate_student_placement(
    current_student: Student,
    db: Session,
) -> bool:
    school = current_student.school
    status_value = (
        school.activation.value
        if school and hasattr(school.activation, "value")
        else (school.activation if school else None)
    )
    if school is None or status_value != ActivationStatus.ACTIVE.value:
        raise HTTPException(
            status_code=403,
            detail="Student access is unavailable for an inactive or missing school.",
        )
    if current_student.class_id is None or current_student.section_id is None:
        return False

    valid_placement = (
        db.query(ClassSection.id)
        .join(
            school_classes,
            school_classes.c.class_id == ClassSection.class_id,
        )
        .filter(
            ClassSection.id == current_student.section_id,
            ClassSection.class_id == current_student.class_id,
            school_classes.c.school_id == current_student.school_id,
        )
        .first()
    )
    if valid_placement is None:
        raise HTTPException(
            status_code=403,
            detail="Student class and section assignment is invalid.",
        )
    return True


def _shared_note_response(note, note_type: str) -> dict:
    return {
        "note_id": note.id,
        "note_type": note_type,
        "name": note.name,
        "content": note.content,
        "status": "shared",
        "school_id": note.school_id,
        "class_id": note.class_id,
        "class_name": note.class_obj.class_name if note.class_obj else None,
        "section_id": note.section_id,
        "section_name": note.section.section_name if note.section else None,
        "subject_id": note.subject_id,
        "subject_name": note.subject.name if note.subject else None,
        "chapter_id": note.chapter_id,
        "chapter_name": note.chapter.chapter_name if note.chapter else None,
        "topic_id": note.topic_id,
        "topic_name": note.topic.topic_name if note.topic else None,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
    }


@router.get("/chapter-notes", status_code=status.HTTP_200_OK)
def get_shared_chapter_notes(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    if not _validate_student_placement(current_student, db):
        return []

    notes = (
        db.query(TeacherChapterNote)
        .join(
            TeacherChapterNoteShare,
            TeacherChapterNoteShare.note_id == TeacherChapterNote.id,
        )
        .options(
            selectinload(TeacherChapterNote.class_obj),
            selectinload(TeacherChapterNote.section),
            selectinload(TeacherChapterNote.subject),
            selectinload(TeacherChapterNote.chapter),
            selectinload(TeacherChapterNote.topic),
        )
        .filter(
            TeacherChapterNote.school_id == current_student.school_id,
            TeacherChapterNote.class_id == current_student.class_id,
            TeacherChapterNote.section_id == current_student.section_id,
            TeacherChapterNoteShare.class_id == current_student.class_id,
            TeacherChapterNoteShare.section_id == current_student.section_id,
            TeacherChapterNote.status == "shared",
            TeacherChapterNote.deleted_at.is_(None),
        )
        .distinct()
        .order_by(TeacherChapterNote.updated_at.desc(), TeacherChapterNote.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_shared_note_response(note, "chapter_note") for note in notes]


@router.get("/teaching-notes", status_code=status.HTTP_200_OK)
def get_shared_teaching_notes(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    if not _validate_student_placement(current_student, db):
        return []

    notes = (
        db.query(TeacherTeachingNote)
        .join(
            TeacherTeachingNoteShare,
            TeacherTeachingNoteShare.note_id == TeacherTeachingNote.id,
        )
        .options(
            selectinload(TeacherTeachingNote.class_obj),
            selectinload(TeacherTeachingNote.section),
            selectinload(TeacherTeachingNote.subject),
            selectinload(TeacherTeachingNote.chapter),
            selectinload(TeacherTeachingNote.topic),
        )
        .filter(
            TeacherTeachingNote.school_id == current_student.school_id,
            TeacherTeachingNote.class_id == current_student.class_id,
            TeacherTeachingNote.section_id == current_student.section_id,
            TeacherTeachingNoteShare.class_id == current_student.class_id,
            TeacherTeachingNoteShare.section_id == current_student.section_id,
            TeacherTeachingNote.status == "shared",
            TeacherTeachingNote.deleted_at.is_(None),
            or_(
                TeacherTeachingNoteShare.student_id.is_(None),
                TeacherTeachingNoteShare.student_id == current_student.id,
            ),
        )
        .distinct()
        .order_by(TeacherTeachingNote.updated_at.desc(), TeacherTeachingNote.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_shared_note_response(note, "teaching_note") for note in notes]


@router.get("/notes", status_code=status.HTTP_200_OK)
def get_shared_teacher_notes(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    if not _validate_student_placement(current_student, db):
        return []

    chapter_notes = (
        db.query(
            literal("chapter_note").label("note_type"),
            TeacherChapterNote.id.label("note_id"),
            TeacherChapterNote.name.label("name"),
            TeacherChapterNote.content.label("content"),
            TeacherChapterNote.status.label("status"),
            TeacherChapterNote.school_id.label("school_id"),
            TeacherChapterNote.class_id.label("class_id"),
            TeacherChapterNote.section_id.label("section_id"),
            TeacherChapterNote.subject_id.label("subject_id"),
            TeacherChapterNote.chapter_id.label("chapter_id"),
            TeacherChapterNote.topic_id.label("topic_id"),
            TeacherChapterNote.created_at.label("created_at"),
            TeacherChapterNote.updated_at.label("updated_at"),
        )
        .join(
            TeacherChapterNoteShare,
            TeacherChapterNoteShare.note_id == TeacherChapterNote.id,
        )
        .filter(
            TeacherChapterNote.school_id == current_student.school_id,
            TeacherChapterNote.class_id == current_student.class_id,
            TeacherChapterNote.section_id == current_student.section_id,
            TeacherChapterNoteShare.class_id == current_student.class_id,
            TeacherChapterNoteShare.section_id == current_student.section_id,
            TeacherChapterNote.status == "shared",
            TeacherChapterNote.deleted_at.is_(None),
        )
        .statement
    )
    teaching_notes = (
        db.query(
            literal("teaching_note").label("note_type"),
            TeacherTeachingNote.id.label("note_id"),
            TeacherTeachingNote.name.label("name"),
            TeacherTeachingNote.content.label("content"),
            TeacherTeachingNote.status.label("status"),
            TeacherTeachingNote.school_id.label("school_id"),
            TeacherTeachingNote.class_id.label("class_id"),
            TeacherTeachingNote.section_id.label("section_id"),
            TeacherTeachingNote.subject_id.label("subject_id"),
            TeacherTeachingNote.chapter_id.label("chapter_id"),
            TeacherTeachingNote.topic_id.label("topic_id"),
            TeacherTeachingNote.created_at.label("created_at"),
            TeacherTeachingNote.updated_at.label("updated_at"),
        )
        .join(
            TeacherTeachingNoteShare,
            TeacherTeachingNoteShare.note_id == TeacherTeachingNote.id,
        )
        .filter(
            TeacherTeachingNote.school_id == current_student.school_id,
            TeacherTeachingNote.class_id == current_student.class_id,
            TeacherTeachingNote.section_id == current_student.section_id,
            TeacherTeachingNoteShare.class_id == current_student.class_id,
            TeacherTeachingNoteShare.section_id == current_student.section_id,
            TeacherTeachingNote.status == "shared",
            TeacherTeachingNote.deleted_at.is_(None),
            or_(
                TeacherTeachingNoteShare.student_id.is_(None),
                TeacherTeachingNoteShare.student_id == current_student.id,
            ),
        )
        .distinct()
        .statement
    )
    shared_notes = union_all(chapter_notes, teaching_notes).subquery()
    rows = (
        db.query(shared_notes)
        .order_by(shared_notes.c.updated_at.desc(), shared_notes.c.note_id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [dict(row._mapping) for row in rows]


@router.get("/homeworks", status_code=status.HTTP_200_OK)
def get_student_homeworks(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    if not _validate_student_placement(current_student, db):
        return []

    homeworks = (
        db.query(TeacherHomework)
        .options(
            selectinload(TeacherHomework.class_obj),
            selectinload(TeacherHomework.section),
        )
        .filter(
            TeacherHomework.school_id == current_student.school_id,
            TeacherHomework.class_id == current_student.class_id,
            TeacherHomework.section_id == current_student.section_id,
            TeacherHomework.status == "published",
        )
        .order_by(TeacherHomework.due_date.asc(), TeacherHomework.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    homework_ids = [homework.id for homework in homeworks]
    submissions_by_homework = {}
    if homework_ids:
        submissions_by_homework = {
            submission.homework_id: submission
            for submission in db.query(TeacherHomeworkSubmission)
            .filter(
                TeacherHomeworkSubmission.homework_id.in_(homework_ids),
                TeacherHomeworkSubmission.student_id == current_student.id,
            )
            .all()
        }

    results = []
    for homework in homeworks:
        submission = submissions_by_homework.get(homework.id)
        results.append({
            "homework_id": homework.id,
            "name": homework.name,
            "class_id": homework.class_id,
            "class_name": homework.class_obj.class_name if homework.class_obj else None,
            "section_id": homework.section_id,
            "section_name": homework.section.section_name if homework.section else None,
            "due_date": homework.due_date,
            "status": homework.status,
            "file_name": homework.original_filename,
            "file_size": homework.file_size,
            "file_url": f"/api/student/homeworks/{homework.id}/file",
            "created_at": homework.created_at,
            "published_at": homework.published_at,
            "is_late": datetime.now(HOMEWORK_TIMEZONE).date() > homework.due_date,
            "my_submission": (
                {
                    "submitted_at": submission.submitted_at,
                    "is_late": submission.is_late,
                    "answer_text": submission.answer_text,
                    "file_name": submission.original_filename,
                    "has_file": submission.file_path is not None,
                }
                if submission is not None
                else None
            ),
        })
    return results


@router.get("/homeworks/{homework_id}/file")
def download_student_homework_file(
    homework_id: int = Path(gt=0),
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    if not _validate_student_placement(current_student, db):
        raise HTTPException(status_code=404, detail="Homework not found.")
    homework = (
        db.query(TeacherHomework)
        .filter(
            TeacherHomework.id == homework_id,
            TeacherHomework.school_id == current_student.school_id,
            TeacherHomework.class_id == current_student.class_id,
            TeacherHomework.section_id == current_student.section_id,
            TeacherHomework.status == "published",
        )
        .first()
    )
    if homework is None:
        raise HTTPException(status_code=404, detail="Homework not found.")
    attachment = resolve_homework_upload(homework.file_path)
    media_type = FILE_MEDIA_TYPES.get(attachment.suffix.lower(), "application/octet-stream")
    return FileResponse(
        attachment,
        media_type=media_type,
        filename=homework.original_filename,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/homeworks/{homework_id}/submissions", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
def submit_student_homework(
    request: Request,
    homework_id: int = Path(gt=0),
    answer_text: str | None = Form(default=None, max_length=MAX_HOMEWORK_ANSWER_LENGTH),
    file: UploadFile | None = File(default=None),
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    _ = request
    if not _validate_student_placement(current_student, db):
        raise HTTPException(status_code=404, detail="Homework not found.")
    homework = (
        db.query(TeacherHomework)
        .filter(
            TeacherHomework.id == homework_id,
            TeacherHomework.school_id == current_student.school_id,
            TeacherHomework.class_id == current_student.class_id,
            TeacherHomework.section_id == current_student.section_id,
            TeacherHomework.status == "published",
        )
        .with_for_update()
        .first()
    )
    if homework is None:
        raise HTTPException(status_code=404, detail="Homework not found.")

    cleaned_answer = answer_text.strip() if answer_text is not None else None
    if cleaned_answer == "":
        cleaned_answer = None
    if cleaned_answer is None and file is None:
        raise HTTPException(
            status_code=422,
            detail="Provide an answer or attach a file.",
        )

    existing = (
        db.query(TeacherHomeworkSubmission)
        .filter(
            TeacherHomeworkSubmission.homework_id == homework.id,
            TeacherHomeworkSubmission.student_id == current_student.id,
        )
        .with_for_update()
        .first()
    )
    old_file_path = existing.file_path if existing is not None else None
    new_file_path = None
    new_filename = None
    new_file_size = None
    if file is not None:
        new_file_path, new_filename, new_file_size = save_homework_upload(file)

    now = datetime.now(timezone.utc)
    is_late = datetime.now(HOMEWORK_TIMEZONE).date() > homework.due_date

    try:
        if existing is None:
            submission = TeacherHomeworkSubmission(
                homework_id=homework.id,
                student_id=current_student.id,
                school_id=current_student.school_id,
                class_id=current_student.class_id,
                section_id=current_student.section_id,
                answer_text=cleaned_answer,
                file_path=new_file_path,
                original_filename=new_filename,
                file_size=new_file_size,
                submitted_at=now,
                is_late=is_late,
            )
            db.add(submission)
        else:
            existing.answer_text = cleaned_answer
            existing.file_path = new_file_path
            existing.original_filename = new_filename
            existing.file_size = new_file_size
            existing.submitted_at = now
            existing.is_late = is_late
        db.commit()
        if old_file_path and old_file_path != new_file_path:
            remove_homework_upload(old_file_path)
    except IntegrityError as exc:
        db.rollback()
        remove_homework_upload(new_file_path)
        raise HTTPException(
            status_code=409,
            detail="A submission was received concurrently. Refresh and retry.",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        remove_homework_upload(new_file_path)
        logger.error("Student homework submission failed: %s.", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail="The homework submission could not be saved.",
        ) from exc

    return {
        "message": "Homework submitted successfully.",
        "homework_id": homework.id,
        "submission_id": submission.id if existing is None else existing.id,
        "submitted_at": now,
        "is_late": is_late,
        "answer_text": cleaned_answer,
        "file_name": new_filename,
        "has_file": new_file_path is not None,
        "replaced_previous_submission": existing is not None,
    }


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


def _exam_start_time(exam: InternalExam) -> datetime:
    start_at = exam.start_at
    if start_at.tzinfo is None:
        return start_at.replace(tzinfo=timezone.utc)
    return start_at.astimezone(timezone.utc)


def _exam_end_time(exam: InternalExam) -> datetime:
    end_at = exam.end_at
    if end_at.tzinfo is None:
        return end_at.replace(tzinfo=timezone.utc)
    return end_at.astimezone(timezone.utc)


def _save_exam_status_changes(db: Session, exams: list[InternalExam]) -> None:
    changed = False
    for exam in exams:
        changed = refresh_internal_exam_status(exam) or changed
    if not changed:
        return
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Student internal exam status update failed: %s.", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Exam statuses could not be updated.") from exc


@router.get("/exams", status_code=status.HTTP_200_OK)
def get_available_student_exams(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    if not _validate_student_placement(current_student, db):
        return {"items": [], "total": 0, "skip": skip, "limit": limit}

    exams = (
        db.query(InternalExam)
        .filter(
            InternalExam.school_id == current_student.school_id,
            InternalExam.class_id == current_student.class_id,
            InternalExam.section_id == current_student.section_id,
            InternalExam.status.in_(("scheduled", "active")),
        )
        .order_by(InternalExam.start_at, InternalExam.id)
        .all()
    )
    _save_exam_status_changes(db, exams)
    listable_query = db.query(InternalExam).filter(
        InternalExam.school_id == current_student.school_id,
        InternalExam.class_id == current_student.class_id,
        InternalExam.section_id == current_student.section_id,
        InternalExam.status.in_(("scheduled", "active")),
    )
    total = listable_query.with_entities(func.count(InternalExam.id)).scalar() or 0
    listable_exams = (
        listable_query.order_by(InternalExam.start_at, InternalExam.id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    exam_ids = [exam.id for exam in listable_exams]
    joined_exam_ids = set()
    if exam_ids:
        joined_exam_ids = {
            attempt.exam_id
            for attempt in db.query(InternalExamAttempt.exam_id).filter(
                InternalExamAttempt.exam_id.in_(exam_ids),
                InternalExamAttempt.student_id == current_student.id,
                InternalExamAttempt.has_joined.is_(True),
            )
        }

    items = [
        {
            "exam_id": exam.id,
            "name": exam.name,
            "type": exam.exam_type.value,
            "subject_id": exam.subject_id,
            "chapter_id": exam.chapter_id,
            "topic_id": exam.topic_id,
            "question_count": exam.question_count,
            "language": exam.language,
            "start_at": exam.start_at,
            "duration_minutes": exam.duration_minutes,
            "status": exam.status,
            "end_at": exam.end_at,
            "has_joined": exam.id in joined_exam_ids,
            "can_join": exam.status == "active" and exam.id not in joined_exam_ids,
        }
        for exam in listable_exams
    ]
    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/exams/{exam_id}", status_code=status.HTTP_200_OK)
def get_student_exam(
    exam_id: int = Path(gt=0),
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    if not _validate_student_placement(current_student, db):
        raise HTTPException(status_code=404, detail="Exam not found.")
    exam = (
        db.query(InternalExam)
        .filter(
            InternalExam.id == exam_id,
            InternalExam.school_id == current_student.school_id,
            InternalExam.class_id == current_student.class_id,
            InternalExam.section_id == current_student.section_id,
            InternalExam.status != "cancelled",
        )
        .first()
    )
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found.")

    _save_exam_status_changes(db, [exam])
    attempt = (
        db.query(InternalExamAttempt.id)
        .filter(
            InternalExamAttempt.exam_id == exam.id,
            InternalExamAttempt.student_id == current_student.id,
            InternalExamAttempt.has_joined.is_(True),
        )
        .first()
    )
    return {
        "exam_id": exam.id,
        "name": exam.name,
        "type": exam.exam_type.value,
        "subject_id": exam.subject_id,
        "chapter_id": exam.chapter_id,
        "topic_id": exam.topic_id,
        "question_count": exam.question_count,
        "language": exam.language,
        "start_at": exam.start_at,
        "end_at": exam.end_at,
        "duration_minutes": exam.duration_minutes,
        "status": exam.status,
        "has_joined": attempt is not None,
        "can_join": exam.status == "active" and attempt is None,
    }


@router.post("/exams/{exam_id}/join", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
def join_student_exam(
    request: Request,
    exam_id: int = Path(gt=0),
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    _ = request
    if not _validate_student_placement(current_student, db):
        raise HTTPException(status_code=404, detail="Exam not found.")
    exam = (
        db.query(InternalExam)
        .options(selectinload(InternalExam.items))
        .filter(
            InternalExam.id == exam_id,
            InternalExam.school_id == current_student.school_id,
            InternalExam.class_id == current_student.class_id,
            InternalExam.section_id == current_student.section_id,
            InternalExam.status != "cancelled",
        )
        .with_for_update()
        .first()
    )
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found.")

    _save_exam_status_changes(db, [exam])
    now = datetime.now(timezone.utc)
    start_at = _exam_start_time(exam)
    end_at = _exam_end_time(exam)
    if exam.status == "completed":
        raise HTTPException(status_code=410, detail="The exam is no longer available.")
    if now < start_at:
        raise HTTPException(status_code=409, detail="The exam has not started yet.")
    if exam.status != "active" or now >= end_at:
        raise HTTPException(status_code=410, detail="The exam is no longer available.")
    if len(exam.items) != exam.question_count:
        logger.error("Exam %s has an inconsistent question item count.", exam.id)
        raise HTTPException(status_code=409, detail="The exam questions are unavailable.")

    previous_attempt = (
        db.query(InternalExamAttempt.id)
        .filter(
            InternalExamAttempt.exam_id == exam.id,
            InternalExamAttempt.student_id == current_student.id,
        )
        .first()
    )
    if previous_attempt is not None:
        raise HTTPException(
            status_code=409,
            detail="You have already joined this exam and cannot join it again.",
        )

    attempt = InternalExamAttempt(
        exam_id=exam.id,
        student_id=current_student.id,
        school_id=current_student.school_id,
        class_id=current_student.class_id,
        section_id=current_student.section_id,
        has_joined=True,
        joined_at=now,
    )
    db.add(attempt)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="You have already joined this exam and cannot join it again.",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Student exam join failed: %s.", type(exc).__name__)
        raise HTTPException(status_code=500, detail="The exam could not be started.") from exc

    return {
        "exam_id": exam.id,
        "attempt_id": attempt.id,
        "has_joined": attempt.has_joined,
        "joined_at": attempt.joined_at,
        "ends_at": end_at,
        "questions": [
            {
                "question_id": item.id,
                "position": item.position,
                "question_text": item.question_text,
                "options": item.options or [],
                "question_type": item.question_type,
                "question_level": item.question_level,
            }
            for item in exam.items
        ],
    }


@router.post("/exams/{exam_id}/submit", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
def submit_student_exam(
    request: Request,
    data: SubmitInternalExamRequest,
    exam_id: int = Path(gt=0),
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    _ = request
    if not _validate_student_placement(current_student, db):
        raise HTTPException(status_code=404, detail="Exam not found.")

    exam = (
        db.query(InternalExam)
        .options(selectinload(InternalExam.items))
        .filter(
            InternalExam.id == exam_id,
            InternalExam.school_id == current_student.school_id,
            InternalExam.class_id == current_student.class_id,
            InternalExam.section_id == current_student.section_id,
            InternalExam.status != "cancelled",
        )
        .with_for_update()
        .first()
    )
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found.")

    _save_exam_status_changes(db, [exam])
    now = datetime.now(timezone.utc)
    if now < _exam_start_time(exam):
        raise HTTPException(status_code=409, detail="The exam has not started yet.")
    if now >= _exam_end_time(exam) or exam.status != "active":
        raise HTTPException(status_code=410, detail="The exam submission period has ended.")
    if len(exam.items) != exam.question_count:
        logger.error("Exam %s has an inconsistent question item count.", exam.id)
        raise HTTPException(status_code=409, detail="The exam questions are unavailable.")

    attempt = (
        db.query(InternalExamAttempt)
        .filter(
            InternalExamAttempt.exam_id == exam.id,
            InternalExamAttempt.student_id == current_student.id,
            InternalExamAttempt.school_id == current_student.school_id,
            InternalExamAttempt.class_id == current_student.class_id,
            InternalExamAttempt.section_id == current_student.section_id,
            InternalExamAttempt.has_joined.is_(True),
        )
        .with_for_update()
        .first()
    )
    if attempt is None:
        raise HTTPException(status_code=403, detail="Join the exam before submitting answers.")
    if db.query(InternalExamResult.id).filter(
        InternalExamResult.exam_id == exam.id,
        InternalExamResult.student_id == current_student.id,
    ).first():
        raise HTTPException(status_code=409, detail="You have already submitted this exam.")

    item_by_id = {item.id: item for item in exam.items}
    submitted_by_id = {answer.question_id: answer.answer for answer in data.answers}
    if set(submitted_by_id) != set(item_by_id):
        raise HTTPException(
            status_code=422,
            detail="Submit exactly one answer for every exam question.",
        )

    total_marks = 0
    max_marks = 0
    pending_count = 0
    responses: list[StudentExamResponse] = []
    for question_id, question in item_by_id.items():
        if not is_supported_exam_question_type(question.question_type):
            logger.error(
                "Exam %s contains unsupported question type %s.",
                exam.id,
                question.question_type,
            )
            raise HTTPException(status_code=409, detail="This exam contains an unsupported question type.")
        max_marks += QUESTION_MARKS[question.question_type]
        try:
            awarded_marks, is_correct = grade_exam_answer(
                question.question_type,
                submitted_by_id[question_id],
                question.answer,
            )
        except ValueError as exc:
            logger.error("Exam %s question grading configuration is invalid.", exam.id)
            raise HTTPException(status_code=409, detail="This exam cannot be graded.") from exc

        if question.question_type == "long_answer":
            pending_count += 1
            grading_status = "pending"
        else:
            total_marks += awarded_marks or 0
            grading_status = "graded"
        responses.append(
            StudentExamResponse(
                exam_id=exam.id,
                question_id=question_id,
                student_answer=submitted_by_id[question_id],
                marks_awarded=awarded_marks,
                is_correct=is_correct,
                grading_status=grading_status,
            )
        )

    result = InternalExamResult(
        exam_id=exam.id,
        student_id=current_student.id,
        total_marks=total_marks,
        max_marks=max_marks,
        grading_status="pending_manual" if pending_count else "graded",
        responses=responses,
    )
    db.add(result)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="You have already submitted this exam.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Student internal exam submission failed: %s.", type(exc).__name__)
        raise HTTPException(status_code=500, detail="The exam submission could not be saved.") from exc

    return {
        "exam_id": exam.id,
        "result_id": result.id,
        "total_marks": total_marks,
        "max_marks": max_marks,
        "grading_status": result.grading_status,
        "pending_manual_grading": pending_count,
        "submitted_at": result.submitted_at,
    }


@router.get("/exams/{exam_id}/result", status_code=status.HTTP_200_OK)
def get_student_exam_result(
    exam_id: int = Path(gt=0),
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    if not _validate_student_placement(current_student, db):
        raise HTTPException(status_code=404, detail="Exam not found.")

    exam = (
        db.query(InternalExam)
        .filter(
            InternalExam.id == exam_id,
            InternalExam.school_id == current_student.school_id,
            InternalExam.class_id == current_student.class_id,
            InternalExam.section_id == current_student.section_id,
            InternalExam.status != "cancelled",
        )
        .first()
    )
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found.")
    _save_exam_status_changes(db, [exam])
    if datetime.now(timezone.utc) < _exam_end_time(exam):
        raise HTTPException(status_code=409, detail="Exam results are available after the exam ends.")

    result = (
        db.query(InternalExamResult)
        .options(
            selectinload(InternalExamResult.responses).selectinload(StudentExamResponse.question)
        )
        .filter(
            InternalExamResult.exam_id == exam.id,
            InternalExamResult.student_id == current_student.id,
        )
        .first()
    )
    if result is None:
        raise HTTPException(status_code=404, detail="No submitted result was found for this exam.")

    return {
        "exam_id": exam.id,
        "result_id": result.id,
        "student_id": result.student_id,
        "total_marks": result.total_marks,
        "max_marks": result.max_marks,
        "grading_status": result.grading_status,
        "submitted_at": result.submitted_at,
        "questions": [
            {
                "question_id": response.question_id,
                "position": response.question.position,
                "question_text": response.question.question_text,
                "question_type": response.question.question_type,
                "student_answer": response.student_answer,
                "correct_answer": response.question.answer,
                "is_correct": response.is_correct,
                "marks_awarded": response.marks_awarded,
                "max_marks": QUESTION_MARKS[response.question.question_type],
                "grading_status": response.grading_status,
            }
            for response in result.responses
        ],
    }