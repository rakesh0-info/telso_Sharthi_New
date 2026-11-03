from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import EmailStr, Field, field_validator, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from databaseCon import get_db
from databaseModel.chapterModel import Chapter
from databaseModel.classModel import (
    ClassModel,
    ClassSection,
    class_subjects,
    school_classes,
)
from databaseModel.classroomOperatorModel import (
    ClassroomOperator,
    ClassroomOperatorAssignment,
)
from databaseModel.contentModel import Content
from databaseModel.questionSetModel import QuestionSet, QuestionSetItem
from databaseModel.schoolModel import School
from databaseModel.studentModel import Student
from databaseModel.subjectModel import Subject
from databaseModel.teacherModel import Teacher
from databaseModel.userModel import User
from databaseModel.schoolAdminAssociation import school_admin_assignments
from enums import ActivationStatus, ContentTypeEnum, GenderEnum, RoleEnum
from jwts.DB_Security_Config import require_roles
from util_validate.password_security import hash_password

from controller.SuperAdminController import (
    RequestModel,
    _clean_email,
    _clean_text,
    _commit,
    _validate_unique_ids,
    _verify_school_active,
)


router = APIRouter(
    prefix="/api/school-admin/schools/{school_id}",
    tags=["School Admin Management"],
)


def _require_school(
    db: Session,
    school_id: int,
    school_admin: User,
) -> School:
    school = db.query(School).filter(School.id == school_id).first()
    if school is None:
        raise HTTPException(status_code=404, detail="School not found.")
    assignment = db.query(school_admin_assignments.c.school_id).filter(
        school_admin_assignments.c.school_id == school_id,
        school_admin_assignments.c.admin_id == school_admin.id,
    ).first()
    if assignment is None:
        raise HTTPException(status_code=404, detail="School not found.")
    _verify_school_active(school)
    return school


def _school_class_ids(db: Session, school_id: int) -> set[int]:
    return {
        row[0]
        for row in db.query(school_classes.c.class_id)
        .filter(school_classes.c.school_id == school_id)
        .all()
    }


def _require_school_classes(
    db: Session,
    school_id: int,
    requested_ids: list[int],
) -> list[ClassModel]:
    _validate_unique_ids(requested_ids)
    if not requested_ids:
        return []
    school_class_ids = _school_class_ids(db, school_id)
    if not set(requested_ids).issubset(school_class_ids):
        raise HTTPException(
            status_code=422,
            detail="Every class must be associated with the selected school.",
        )
    return (
        db.query(ClassModel)
        .filter(ClassModel.id.in_(requested_ids))
        .order_by(ClassModel.id)
        .all()
    )


def _require_school_sections(
    db: Session,
    school_id: int,
    class_ids: list[int],
    section_ids: list[int],
) -> list[ClassSection]:
    _validate_unique_ids(section_ids)
    if section_ids and not class_ids:
        raise HTTPException(
            status_code=422,
            detail="class_ids are required when section_ids are provided.",
        )
    if not section_ids:
        return []
    sections = (
        db.query(ClassSection)
        .filter(ClassSection.id.in_(section_ids))
        .all()
    )
    if len(sections) != len(section_ids):
        raise HTTPException(status_code=422, detail="One or more sections are invalid.")
    school_class_ids = _school_class_ids(db, school_id)
    if any(
        section.class_id not in class_ids
        or section.class_id not in school_class_ids
        for section in sections
    ):
        raise HTTPException(
            status_code=422,
            detail="Each section must belong to an assigned class in the selected school.",
        )
    if len({section.class_id for section in sections}) != len(sections):
        raise HTTPException(
            status_code=422,
            detail="Only one section per class can be assigned to a teacher.",
        )
    return sections


def _require_school_subjects(
    db: Session,
    school_id: int,
    class_ids: list[int],
    subject_ids: list[int],
) -> list[Subject]:
    _validate_unique_ids(subject_ids)
    if not subject_ids:
        return []
    if not class_ids:
        raise HTTPException(
            status_code=422,
            detail="class_ids are required when subject_ids are provided.",
        )
    allowed_subject_ids = {
        row[0]
        for row in (
            db.query(class_subjects.c.subject_id)
            .join(
                school_classes,
                school_classes.c.class_id == class_subjects.c.class_id,
            )
            .filter(
                school_classes.c.school_id == school_id,
                class_subjects.c.class_id.in_(class_ids),
            )
            .distinct()
            .all()
        )
    }
    if not set(subject_ids).issubset(allowed_subject_ids):
        raise HTTPException(
            status_code=422,
            detail="Every subject must be assigned to one of the selected school classes.",
        )
    return (
        db.query(Subject)
        .filter(Subject.id.in_(subject_ids))
        .order_by(Subject.id)
        .all()
    )


class SchoolAdminTeacherCreate(RequestModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone_number: Optional[str] = Field(default=None, pattern=r"^\d{10}$")
    gender: Optional[GenderEnum] = None
    qualification: Optional[str] = Field(default=None, max_length=255)
    class_ids: list[int] = Field(default_factory=list, max_length=100)
    section_ids: list[int] = Field(default_factory=list, max_length=100)
    subject_ids: list[int] = Field(default_factory=list, max_length=100)
    activation_status: ActivationStatus = ActivationStatus.ACTIVE

    @field_validator("name", "qualification", mode="before")
    @classmethod
    def strip_text(cls, value):
        return _clean_text(value) if value is not None else None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return _clean_email(value)

    @field_validator("class_ids", "section_ids", "subject_ids")
    @classmethod
    def validate_ids(cls, value):
        if any(item <= 0 for item in value):
            raise ValueError("IDs must be positive integers.")
        return _validate_unique_ids(value)


class SchoolAdminStudentCreate(RequestModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    gender: Optional[GenderEnum] = None
    dob: Optional[date] = None
    phone_number: Optional[str] = Field(default=None, pattern=r"^\d{10}$")
    class_id: Optional[int] = Field(default=None, gt=0)
    section_id: Optional[int] = Field(default=None, gt=0)
    parents_name: Optional[str] = Field(default=None, max_length=255)
    parents_ph_no: Optional[str] = Field(default=None, pattern=r"^\d{10}$")
    parents_email: Optional[EmailStr] = None

    @field_validator("name", "parents_name", mode="before")
    @classmethod
    def strip_text(cls, value):
        return _clean_text(value) if value is not None else None

    @field_validator("email", "parents_email")
    @classmethod
    def normalize_email(cls, value):
        return _clean_email(value) if value is not None else None

    @model_validator(mode="after")
    def validate_student_data(self):
        if self.dob and self.dob > date.today():
            raise ValueError("Date of birth cannot be in the future.")
        if self.section_id is not None and self.class_id is None:
            raise ValueError("class_id is required when section_id is provided.")
        return self


class SchoolAdminOperatorCreate(RequestModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone_number: Optional[str] = Field(default=None, pattern=r"^\d{10}$")
    gender: Optional[GenderEnum] = None
    class_ids: list[int] = Field(default_factory=list, max_length=100)
    activation_status: ActivationStatus = ActivationStatus.ACTIVE

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value):
        return _clean_text(value)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return _clean_email(value)

    @field_validator("class_ids")
    @classmethod
    def validate_class_ids(cls, value):
        if any(item <= 0 for item in value):
            raise ValueError("IDs must be positive integers.")
        return _validate_unique_ids(value)


@router.get("/classes")
def get_school_classes(
    school_id: int,
    school_admin: User = Depends(require_roles(RoleEnum.SCHOOL_ADMIN)),
    db: Session = Depends(get_db),
):
    _require_school(db, school_id, school_admin)
    classes = (
        db.query(ClassModel)
        .join(school_classes, school_classes.c.class_id == ClassModel.id)
        .options(selectinload(ClassModel.sections))
        .filter(school_classes.c.school_id == school_id)
        .order_by(ClassModel.id)
        .all()
    )
    return [
        {
            "class_id": class_obj.id,
            "class_name": class_obj.class_name,
            "grade_level": class_obj.grade_level,
            "sections": [
                {"section_id": section.id, "section_name": section.section_name}
                for section in sorted(class_obj.sections, key=lambda section: section.id)
            ],
        }
        for class_obj in classes
    ]


@router.get("/teachers")
def get_school_teachers(
    school_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    school_admin: User = Depends(require_roles(RoleEnum.SCHOOL_ADMIN)),
    db: Session = Depends(get_db),
):
    school = _require_school(db, school_id, school_admin)
    teachers = (
        db.query(Teacher)
        .options(
            selectinload(Teacher.user),
            selectinload(Teacher.classes),
            selectinload(Teacher.sections).selectinload(ClassSection.class_obj),
            selectinload(Teacher.subjects),
        )
        .filter(Teacher.school_id == school.id)
        .order_by(Teacher.id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        {
            "teacher_id": teacher.id,
            "user_id": teacher.user.id if teacher.user else None,
            "name": teacher.user.name if teacher.user else None,
            "email": teacher.user.email if teacher.user else None,
            "phone_number": teacher.user.phone_number if teacher.user else None,
            "gender": (
                teacher.user.gender.value
                if teacher.user and hasattr(teacher.user.gender, "value")
                else (teacher.user.gender if teacher.user else None)
            ),
            "school_id": teacher.school_id,
            "school_name": school.name,
            "qualification": teacher.qualification,
            "assigned_classes": [
                {"class_id": class_obj.id, "class_name": class_obj.class_name}
                for class_obj in teacher.classes
            ],
            "assigned_sections": [
                {
                    "section_id": section.id,
                    "section_name": section.section_name,
                    "class_id": section.class_id,
                    "class_name": (
                        section.class_obj.class_name if section.class_obj else None
                    ),
                }
                for section in teacher.sections
            ],
            "assigned_subjects": [
                {"subject_id": subject.id, "subject_name": subject.name}
                for subject in teacher.subjects
            ],
            "activation_status": (
                teacher.user.activation_status.value
                if teacher.user and hasattr(teacher.user.activation_status, "value")
                else (
                    teacher.user.activation_status if teacher.user else None
                )
            ),
        }
        for teacher in teachers
    ]


@router.get("/students")
def get_school_students(
    school_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    school_admin: User = Depends(require_roles(RoleEnum.SCHOOL_ADMIN)),
    db: Session = Depends(get_db),
):
    school = _require_school(db, school_id, school_admin)
    students = (
        db.query(Student)
        .options(
            selectinload(Student.class_obj),
            selectinload(Student.section_obj),
        )
        .filter(Student.school_id == school.id)
        .order_by(Student.id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        {
            "student_id": student.id,
            "name": student.name,
            "email": student.email,
            "gender": (
                student.gender.value
                if hasattr(student.gender, "value")
                else student.gender
            ),
            "dob": student.dob,
            "phone_number": student.phone_number,
            "school_id": student.school_id,
            "school_name": school.name,
            "class_id": student.class_id,
            "class_name": (
                student.class_obj.class_name if student.class_obj else None
            ),
            "section_id": student.section_id,
            "section_name": (
                student.section_obj.section_name if student.section_obj else None
            ),
            "parents_name": student.parents_name,
            "parents_ph_no": student.parents_ph_no,
            "parents_email": student.parents_email,
        }
        for student in students
    ]


@router.get("/classroom-operators")
def get_school_classroom_operators(
    school_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    school_admin: User = Depends(require_roles(RoleEnum.SCHOOL_ADMIN)),
    db: Session = Depends(get_db),
):
    school = _require_school(db, school_id, school_admin)
    operators = (
        db.query(ClassroomOperator)
        .options(
            selectinload(ClassroomOperator.user),
            selectinload(ClassroomOperator.class_assignments).selectinload(
                ClassroomOperatorAssignment.class_obj
            ),
        )
        .filter(ClassroomOperator.school_id == school.id)
        .order_by(ClassroomOperator.id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        {
            "operator_id": operator.id,
            "user_id": operator.user.id if operator.user else None,
            "name": operator.user.name if operator.user else None,
            "email": operator.user.email if operator.user else None,
            "phone_number": (
                operator.user.phone_number if operator.user else None
            ),
            "gender": (
                operator.user.gender.value
                if operator.user and hasattr(operator.user.gender, "value")
                else (operator.user.gender if operator.user else None)
            ),
            "school_id": operator.school_id,
            "school_name": school.name,
            "assigned_classes": [
                {
                    "class_id": assignment.class_obj.id,
                    "class_name": assignment.class_obj.class_name,
                }
                for assignment in operator.class_assignments
                if assignment.class_obj is not None
            ],
            "activation_status": (
                operator.user.activation_status.value
                if operator.user
                and hasattr(operator.user.activation_status, "value")
                else (
                    operator.user.activation_status if operator.user else None
                )
            ),
        }
        for operator in operators
    ]


@router.get("/subjects")
def get_school_subjects(
    school_id: int,
    class_id: Optional[int] = Query(default=None, gt=0),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    school_admin: User = Depends(require_roles(RoleEnum.SCHOOL_ADMIN)),
    db: Session = Depends(get_db),
):
    _require_school(db, school_id, school_admin)
    school_class_ids = _school_class_ids(db, school_id)
    if class_id is not None:
        if class_id not in school_class_ids:
            raise HTTPException(status_code=404, detail="Class not found for this school.")
        school_class_ids = {class_id}
    if not school_class_ids:
        return []

    subjects = (
        db.query(Subject)
        .join(class_subjects, class_subjects.c.subject_id == Subject.id)
        .filter(class_subjects.c.class_id.in_(school_class_ids))
        .distinct()
        .order_by(Subject.id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    if not subjects:
        return []
    subject_ids = [subject.id for subject in subjects]
    subject_rows = (
        db.query(Subject.id, class_subjects.c.class_id)
        .join(class_subjects, class_subjects.c.subject_id == Subject.id)
        .filter(
            Subject.id.in_(subject_ids),
            class_subjects.c.class_id.in_(school_class_ids),
        )
        .all()
    )
    class_ids_by_subject: dict[int, set[int]] = {}
    for subject, linked_class_id in subject_rows:
        class_ids_by_subject.setdefault(subject, set()).add(linked_class_id)

    chapters = (
        db.query(Chapter)
        .options(selectinload(Chapter.topics))
        .filter(Chapter.subject_id.in_([subject.id for subject in subjects]))
        .order_by(Chapter.id)
        .all()
    )
    chapters_by_subject: dict[int, list[Chapter]] = {}
    for chapter in chapters:
        chapters_by_subject.setdefault(chapter.subject_id, []).append(chapter)

    return [
        {
            "subject_id": subject.id,
            "subject_name": subject.name,
            "class_ids": sorted(class_ids_by_subject[subject.id]),
            "chapters": [
                {
                    "chapter_id": chapter.id,
                    "chapter_name": chapter.chapter_name,
                    "topics": [
                        {
                            "topic_id": topic.id,
                            "topic_name": topic.topic_name,
                            "description": topic.description,
                        }
                        for topic in sorted(chapter.topics, key=lambda topic: topic.id)
                    ],
                }
                for chapter in chapters_by_subject.get(subject.id, [])
            ],
        }
        for subject in subjects
    ]


@router.get("/content")
def get_school_content(
    school_id: int,
    class_id: Optional[int] = Query(default=None, gt=0),
    content_type: Optional[ContentTypeEnum] = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    school_admin: User = Depends(require_roles(RoleEnum.SCHOOL_ADMIN)),
    db: Session = Depends(get_db),
):
    _require_school(db, school_id, school_admin)
    school_class_ids = _school_class_ids(db, school_id)
    if class_id is not None:
        if class_id not in school_class_ids:
            raise HTTPException(status_code=404, detail="Class not found for this school.")
        school_class_ids = {class_id}
    if not school_class_ids:
        return []

    query = (
        db.query(Content)
        .options(
            selectinload(Content.uploader),
            selectinload(Content.class_obj),
            selectinload(Content.subject),
            selectinload(Content.chapter),
            selectinload(Content.topic),
        )
        .filter(
            Content.school_id == school_id,
            Content.class_id.in_(school_class_ids),
        )
    )
    if content_type is not None:
        query = query.filter(Content.content_type == content_type)
    items = query.order_by(Content.id).offset(skip).limit(limit).all()
    return [
        {
            "content_id": item.id,
            "content_type": item.content_type.value,
            "title": item.title,
            "content_code": item.content_code,
            "description": item.description,
            "school_id": item.school_id,
            "class_id": item.class_id,
            "class_name": item.class_obj.class_name if item.class_obj else None,
            "subject_id": item.subject_id,
            "subject_name": item.subject.name if item.subject else None,
            "chapter_id": item.chapter_id,
            "chapter_name": item.chapter.chapter_name if item.chapter else None,
            "topic_id": item.topic_id,
            "topic_name": item.topic.topic_name if item.topic else None,
            "keywords": item.keywords,
            "english_file_url": item.english_file_url,
            "manipuri_file_url": item.manipuri_file_url,
            "uploaded_by": item.uploaded_by,
            "uploader_name": item.uploader.name if item.uploader else None,
            "uploader_email": item.uploader.email if item.uploader else None,
        }
        for item in items
    ]


@router.get("/question-sets")
def get_school_question_sets(
    school_id: int,
    class_id: Optional[int] = Query(default=None, gt=0),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    school_admin: User = Depends(require_roles(RoleEnum.SCHOOL_ADMIN)),
    db: Session = Depends(get_db),
):
    _require_school(db, school_id, school_admin)
    if class_id is not None:
        if class_id not in _school_class_ids(db, school_id):
            raise HTTPException(status_code=404, detail="Class not found for this school.")

    query = (
        db.query(QuestionSet)
        .options(
            selectinload(QuestionSet.class_obj),
            selectinload(QuestionSet.section),
            selectinload(QuestionSet.subject),
            selectinload(QuestionSet.chapter),
            selectinload(QuestionSet.topic),
            selectinload(QuestionSet.creator),
            selectinload(QuestionSet.items).selectinload(QuestionSetItem.question),
        )
        .filter(QuestionSet.school_id == school_id)
        .order_by(QuestionSet.created_at.desc(), QuestionSet.id.desc())
    )
    if class_id is not None:
        query = query.filter(QuestionSet.class_id == class_id)
    sets = (
        query
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        {
            "question_set_id": question_set.id,
            "name": question_set.name,
            "school_id": question_set.school_id,
            "class_id": question_set.class_id,
            "class_name": question_set.class_obj.class_name if question_set.class_obj else None,
            "section_id": question_set.section_id,
            "section_name": question_set.section.section_name if question_set.section else None,
            "subject_id": question_set.subject_id,
            "subject_name": question_set.subject.name if question_set.subject else None,
            "chapter_id": question_set.chapter_id,
            "chapter_name": question_set.chapter.chapter_name if question_set.chapter else None,
            "topic_id": question_set.topic_id,
            "topic_name": question_set.topic.topic_name if question_set.topic else None,
            "language": question_set.language,
            "question_count": question_set.question_count,
            "question_type": question_set.question_type,
            "question_level": question_set.question_level,
            "created_at": question_set.created_at,
            "scheduled_at": question_set.scheduled_at,
            "duration_minutes": question_set.duration_minutes,
            "created_by": question_set.created_by,
            "creator_name": question_set.creator.name if question_set.creator else None,
            "creator_email": question_set.creator.email if question_set.creator else None,
            "items": [
                {
                    "question_set_item_id": item.id,
                    "question_id": item.question_id,
                    "position": item.position,
                    "answer": item.answer,
                    "question_text": item.question.question_text if item.question else None,
                    "options": item.question.options if item.question else None,
                    "question_type": item.question.question_type if item.question else None,
                    "question_level": item.question.question_level if item.question else None,
                    "language": item.question.language if item.question else None,
                }
                for item in question_set.items
            ],
        }
        for question_set in sets
    ]


@router.post(
    "/teachers",
    status_code=status.HTTP_201_CREATED,
)
def add_school_teacher(
    school_id: int,
    data: SchoolAdminTeacherCreate,
    school_admin: User = Depends(require_roles(RoleEnum.SCHOOL_ADMIN)),
    db: Session = Depends(get_db),
):
    school = _require_school(db, school_id, school_admin)
    if db.query(User.id).filter(func.lower(User.email) == data.email).first():
        raise HTTPException(status_code=409, detail="Email already registered.")
    classes = _require_school_classes(db, school_id, data.class_ids)
    sections = _require_school_sections(
        db, school_id, data.class_ids, data.section_ids
    )
    subjects = _require_school_subjects(
        db, school_id, data.class_ids, data.subject_ids
    )

    user = User(
        name=data.name,
        email=data.email,
        password=hash_password(data.password),
        phone_number=data.phone_number,
        gender=data.gender,
        role=RoleEnum.TEACHER,
        activation_status=data.activation_status,
    )
    teacher = Teacher(school_id=school.id, qualification=data.qualification)
    teacher.classes = classes
    teacher.sections = sections
    teacher.subjects = subjects
    user.teacher_profile = teacher
    db.add(user)
    db.query(School).filter(School.id == school.id).update(
        {School.total_teacher: School.total_teacher + 1},
        synchronize_session=False,
    )
    _commit(db, "Teacher email or assignment conflicts with existing data.")
    db.refresh(teacher)
    return {
        "message": "Teacher created successfully.",
        "teacher_id": teacher.id,
        "user_id": user.id,
    }


@router.post(
    "/students",
    status_code=status.HTTP_201_CREATED,
)
def add_school_student(
    school_id: int,
    data: SchoolAdminStudentCreate,
    school_admin: User = Depends(require_roles(RoleEnum.SCHOOL_ADMIN)),
    db: Session = Depends(get_db),
):
    school = _require_school(db, school_id, school_admin)
    if db.query(Student.id).filter(func.lower(Student.email) == data.email).first():
        raise HTTPException(status_code=409, detail="Student email already exists.")

    if data.class_id is not None:
        _require_school_classes(db, school_id, [data.class_id])
    if data.section_id is not None:
        _require_school_sections(
            db, school_id, [data.class_id], [data.section_id]
        )
    student = Student(
        **data.model_dump(),
        school_id=school.id,
    )
    db.add(student)
    db.query(School).filter(School.id == school.id).update(
        {School.total_student: School.total_student + 1},
        synchronize_session=False,
    )
    _commit(db, "Student email or parent email already exists.")
    db.refresh(student)
    return {
        "message": "Student profile created successfully.",
        "student_id": student.id,
    }


@router.post(
    "/classroom-operators",
    status_code=status.HTTP_201_CREATED,
)
def add_school_classroom_operator(
    school_id: int,
    data: SchoolAdminOperatorCreate,
    school_admin: User = Depends(require_roles(RoleEnum.SCHOOL_ADMIN)),
    db: Session = Depends(get_db),
):
    school = _require_school(db, school_id, school_admin)
    if db.query(User.id).filter(func.lower(User.email) == data.email).first():
        raise HTTPException(status_code=409, detail="Email already registered.")
    classes = _require_school_classes(db, school_id, data.class_ids)

    user = User(
        name=data.name,
        email=data.email,
        password=hash_password(data.password),
        phone_number=data.phone_number,
        gender=data.gender,
        role=RoleEnum.CLASSROOM_OPERATOR,
        activation_status=data.activation_status,
    )
    operator = ClassroomOperator(school_id=school.id)
    for class_obj in classes:
        operator.class_assignments.append(
            ClassroomOperatorAssignment(class_id=class_obj.id)
        )
    user.operator_profile = operator
    db.add(user)
    _commit(db, "Classroom operator email or assignment conflicts with existing data.")
    db.refresh(operator)
    return {
        "message": "Classroom operator created successfully.",
        "operator_id": operator.id,
        "user_id": user.id,
    }
