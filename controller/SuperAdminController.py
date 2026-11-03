from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from databaseCon import get_db
from databaseModel.userModel import User
from databaseModel.schoolModel import School
from databaseModel.classModel import ClassModel, ClassSection, class_subjects, school_classes
from databaseModel.teacherModel import Teacher
from databaseModel.studentModel import Student
from databaseModel.classroomOperatorModel import ClassroomOperator, ClassroomOperatorAssignment
from databaseModel.subjectModel import Subject
from databaseModel.chapterModel import Chapter, Topic
from databaseModel.questionSetModel import QuestionSet
from databaseModel.teacherLessonModel import TeacherLessonContent, TeacherLessonShare
from enums import RoleEnum, ActivationStatus, GenderEnum
from util_validate.password_security import hash_password
from jwts.DB_Security_Config import require_roles

router = APIRouter(prefix="/api/super-admin", tags=["Super Admin Management"])
verify_super_admin = Depends(require_roles(RoleEnum.SUPER_ADMIN))


# ---------------------------------------------------------------------------
# Shared validation helpers
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


def _clean_email(value: EmailStr) -> str:
    return str(value).strip().lower()


def _validate_unique_ids(values: list[int]) -> list[int]:
    if len(values) != len(set(values)):
        raise ValueError("Duplicate IDs are not allowed.")
    return values


def _validate_positive_ids(values: list[int]) -> list[int]:
    if any(value <= 0 for value in values):
        raise ValueError("IDs must be positive integers.")
    return _validate_unique_ids(values)


def _commit(db: Session, detail: str = "The requested record conflicts with existing data.") -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Do not expose SQL, table names, or database constraint details.
        raise HTTPException(status_code=409, detail=detail) from exc


def _require_nonempty_update(data: BaseModel) -> None:
    if not data.model_fields_set:
        raise HTTPException(status_code=400, detail="At least one field must be provided.")


def _get_school_admin(db: Session, admin_id: int) -> User:
    admin = db.query(User).filter(
        User.id == admin_id,
        User.role == RoleEnum.SCHOOL_ADMIN,
    ).first()
    if not admin:
        raise HTTPException(status_code=404, detail=f"School Admin {admin_id} not found.")
    return admin


def _get_school_admins(db: Session, admin_ids: list[int]) -> list[User]:
    _validate_unique_ids(admin_ids)
    if not admin_ids:
        return []
    admins = db.query(User).filter(
        User.id.in_(admin_ids), User.role == RoleEnum.SCHOOL_ADMIN
    ).all()
    found = {admin.id for admin in admins}
    missing = sorted(set(admin_ids) - found)
    if missing:
        raise HTTPException(status_code=404, detail=f"School Admin IDs not found or not School Admin accounts: {missing}")
    inactive = [admin.id for admin in admins if admin.activation_status != ActivationStatus.ACTIVE]
    if inactive:
        raise HTTPException(status_code=409, detail=f"Inactive School Admin accounts cannot be assigned: {sorted(inactive)}")
    by_id = {admin.id: admin for admin in admins}
    return [by_id[admin_id] for admin_id in admin_ids]


def _generate_temporary_password(length: int = 20) -> str:
    """Generate a cryptographically strong, printable temporary password."""
    if length < 16:
        raise ValueError("Temporary password length must be at least 16.")
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in password) and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password)
                and any(c in "!@#$%^&*()-_=+" for c in password)):
            return password


def _get_class(db: Session, class_id: int) -> ClassModel:
    obj = db.query(ClassModel).filter(ClassModel.id == class_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail=f"Class {class_id} not found.")
    return obj


def _get_section(db: Session, section_id: int) -> ClassSection:
    obj = db.query(ClassSection).filter(ClassSection.id == section_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail=f"Section {section_id} not found.")
    return obj


def _get_many(db: Session, model, ids: list[int], label: str):
    _validate_unique_ids(ids)
    if not ids:
        return []
    rows = db.query(model).filter(model.id.in_(ids)).all()
    if len(rows) != len(ids):
        found = {row.id for row in rows}
        missing = sorted(set(ids) - found)
        raise HTTPException(status_code=400, detail=f"Invalid {label} IDs: {missing}")
    return rows


def _get_school_classes(db: Session, class_ids: list[int]) -> list[ClassModel]:
    _validate_unique_ids(class_ids)
    classes = (
        db.query(ClassModel)
        .options(selectinload(ClassModel.sections))
        .filter(ClassModel.id.in_(class_ids))
        .order_by(ClassModel.id)
        .all()
    )
    if len(classes) != len(class_ids):
        found = {class_obj.id for class_obj in classes}
        missing = sorted(set(class_ids) - found)
        raise HTTPException(status_code=400, detail=f"Invalid class IDs: {missing}")
    without_sections = [
        class_obj.id for class_obj in classes if not class_obj.sections
    ]
    if without_sections:
        raise HTTPException(
            status_code=422,
            detail=f"Every assigned class must have at least one section: {without_sections}",
        )
    return classes


def _format_school_classes(classes: list[ClassModel]) -> list[dict]:
    return [
        {
            "class_id": class_obj.id,
            "class_name": class_obj.class_name,
            "sections": [
                {"section_id": section.id, "section_name": section.section_name}
                for section in class_obj.sections
            ],
        }
        for class_obj in classes
    ]


def _require_school_classes(
    db: Session,
    school_id: int,
    class_ids: list[int],
) -> list[ClassModel]:
    classes = _get_many(db, ClassModel, class_ids, "class")
    if not class_ids:
        return classes
    assigned_class_ids = {
        row[0]
        for row in db.query(school_classes.c.class_id)
        .filter(
            school_classes.c.school_id == school_id,
            school_classes.c.class_id.in_(class_ids),
        )
        .all()
    }
    unassigned_class_ids = sorted(set(class_ids) - assigned_class_ids)
    if unassigned_class_ids:
        raise HTTPException(
            status_code=422,
            detail=f"Classes are not assigned to school {school_id}: {unassigned_class_ids}",
        )
    return classes


def _validate_teacher_subjects(
    db: Session,
    class_ids: list[int],
    subject_ids: list[int],
) -> list[Subject]:
    subjects = _get_many(db, Subject, subject_ids, "subject")
    if not subject_ids:
        return subjects
    if not class_ids:
        raise HTTPException(
            status_code=422,
            detail="class_ids are required when subject_ids are provided.",
        )
    assigned_subject_ids = {
        row[0]
        for row in db.query(class_subjects.c.subject_id)
        .filter(
            class_subjects.c.class_id.in_(class_ids),
            class_subjects.c.subject_id.in_(subject_ids),
        )
        .distinct()
        .all()
    }
    unassigned_subject_ids = sorted(set(subject_ids) - assigned_subject_ids)
    if unassigned_subject_ids:
        raise HTTPException(
            status_code=422,
            detail=f"Subjects must be assigned to one of the teacher's classes: {unassigned_subject_ids}",
        )
    return subjects


def _validate_student_placement(
    db: Session,
    school_id: int,
    class_id: Optional[int],
    section_id: Optional[int],
) -> None:
    if section_id is not None and class_id is None:
        raise HTTPException(status_code=422, detail="class_id is required when section_id is provided.")
    if class_id is not None:
        _get_class(db, class_id)
        _require_school_classes(db, school_id, [class_id])
    if section_id is not None:
        section = _get_section(db, section_id)
        if section.class_id != class_id:
            raise HTTPException(status_code=422, detail="The selected section does not belong to the selected class.")


def _validate_teacher_sections(
    db: Session,
    class_ids: list[int],
    section_ids: list[int],
) -> list[ClassSection]:
    sections = _get_many(db, ClassSection, section_ids, "section")
    section_class_ids = [section.class_id for section in sections]
    if any(class_id not in class_ids for class_id in section_class_ids):
        raise HTTPException(status_code=422, detail="Each selected section must belong to an assigned class.")
    if len(section_class_ids) != len(set(section_class_ids)):
        raise HTTPException(status_code=422, detail="Only one section per class can be assigned to a teacher.")
    return sections


def _verify_school_active(school: School) -> None:
    status_val = school.activation.value if hasattr(school.activation, "value") else school.activation
    if status_val != ActivationStatus.ACTIVE.value and status_val != ActivationStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Operation not allowed on an inactive school.")


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class SchoolCreate(RequestModel):
    name: str = Field(min_length=2, max_length=255)
    school_code: str = Field(min_length=2, max_length=50)
    class_ids: list[int] = Field(min_length=1, max_length=100)
    state: Optional[str] = Field(default=None, max_length=100)
    district: Optional[str] = Field(default=None, max_length=100)
    region: Optional[str] = Field(default=None, max_length=100)
    school_ph_no: Optional[str] = Field(default=None, pattern=r"^\d{10}$")
    address: Optional[str] = Field(default=None, max_length=200)
    school_admin_ids: list[int] = Field(default_factory=list, max_length=100)
    activation: ActivationStatus = ActivationStatus.ACTIVE

    @field_validator("name", "school_code", "state", "district", "region", "address", mode="before")
    @classmethod
    def strip_text(cls, value):
        return _clean_text(value) if value is not None else None

    @field_validator("school_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.upper()

    @field_validator("class_ids")
    @classmethod
    def validate_class_ids(cls, value):
        return _validate_positive_ids(value)

    @field_validator("school_admin_ids")
    @classmethod
    def unique_admin_ids(cls, value):
        return _validate_positive_ids(value)


class SchoolUpdate(RequestModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    school_code: Optional[str] = Field(default=None, min_length=2, max_length=50)
    state: Optional[str] = Field(default=None, max_length=100)
    district: Optional[str] = Field(default=None, max_length=100)
    region: Optional[str] = Field(default=None, max_length=100)
    school_ph_no: Optional[str] = Field(default=None, pattern=r"^\d{10}$")
    address: Optional[str] = Field(default=None, max_length=200)
    activation: Optional[ActivationStatus] = None

    @field_validator("name", "school_code", "state", "district", "region", "address", mode="before")
    @classmethod
    def strip_text(cls, value):
        return _clean_text(value) if value is not None else None

    @field_validator("school_code")
    @classmethod
    def normalize_code(cls, value):
        return value.upper() if value is not None else value


class SchoolAdminCreate(RequestModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    phone_number: Optional[str] = Field(default=None, pattern=r"^\d{10}$")
    gender: Optional[GenderEnum] = None
    activation_status: ActivationStatus = ActivationStatus.ACTIVE

    @field_validator("name")
    @classmethod
    def strip_name(cls, value):
        return _clean_text(value)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return _clean_email(value)


class SchoolAdminUpdate(RequestModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = Field(default=None, pattern=r"^\d{10}$")
    gender: Optional[GenderEnum] = None
    activation_status: Optional[ActivationStatus] = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value):
        return _clean_text(value) if value is not None else None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return _clean_email(value) if value is not None else value


class ContentAdminCreate(RequestModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    phone_number: Optional[str] = Field(default=None, pattern=r"^\d{10}$")
    gender: Optional[GenderEnum] = None
    activation_status: ActivationStatus = ActivationStatus.ACTIVE
    

    @field_validator("name")
    @classmethod
    def strip_name(cls, value):
        return _clean_text(value)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return _clean_email(value)


class ContentAdminUpdate(RequestModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = Field(default=None, pattern=r"^\d{10}$")
    gender: Optional[GenderEnum] = None
    activation_status: Optional[ActivationStatus] = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value):
        return _clean_text(value) if value is not None else None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return _clean_email(value) if value is not None else value


class SchoolAssignmentUpdate(RequestModel):
    admin_ids: list[int] = Field(max_length=100)

    @field_validator("admin_ids")
    @classmethod
    def unique_admin_ids(cls, value):
        return _validate_positive_ids(value)


class TeacherCreate(RequestModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone_number: Optional[str] = Field(default=None, pattern=r"^\d{10}$")
    gender: Optional[GenderEnum] = None
    school_id: int = Field(gt=0)
    qualification: Optional[str] = Field(default=None, max_length=255)
    class_ids: list[int] = Field(default_factory=list)
    section_ids: list[int] = Field(default_factory=list)
    subject_ids: list[int] = Field(default_factory=list)
    activation_status: ActivationStatus = ActivationStatus.ACTIVE

    @field_validator("name", "qualification")
    @classmethod
    def strip_text(cls, value):
        return _clean_text(value) if value is not None else None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return _clean_email(value)

    @field_validator("class_ids", "section_ids", "subject_ids")
    @classmethod
    def unique_ids(cls, value):
        return _validate_positive_ids(value)


class TeacherUpdate(RequestModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = Field(default=None, pattern=r"^\d{10}$")
    gender: Optional[GenderEnum] = None
    qualification: Optional[str] = Field(default=None, max_length=255)
    activation_status: Optional[ActivationStatus] = None

    @field_validator("name", "qualification")
    @classmethod
    def strip_text(cls, value):
        return _clean_text(value) if value is not None else None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return _clean_email(value) if value is not None else value


class TeacherAssignmentUpdate(RequestModel):
    class_ids: list[int] = Field(default_factory=list)
    section_ids: list[int] = Field(default_factory=list)
    subject_ids: list[int] = Field(default_factory=list)

    @field_validator("class_ids", "section_ids", "subject_ids")
    @classmethod
    def unique_ids(cls, value):
        return _validate_positive_ids(value)


class ClassWithSectionCreate(RequestModel):
    class_name: str = Field(min_length=1, max_length=100)
    grade_level: Optional[str] = Field(default=None, max_length=50)
    sections: list[str] = Field(min_length=1, max_length=100)
    school_ids: list[int] = Field(default_factory=list, max_length=100)

    @field_validator("class_name", "grade_level")
    @classmethod
    def strip_text(cls, value):
        return _clean_text(value) if value is not None else None

    @field_validator("sections")
    @classmethod
    def normalize_sections(cls, values):
        cleaned = [_clean_text(v) for v in values]
        normalized = [v.upper() for v in cleaned]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Duplicate section names are not allowed.")
        if any(len(v) > 20 for v in normalized):
            raise ValueError("Section names cannot exceed 20 characters.")
        return normalized

    @field_validator("school_ids")
    @classmethod
    def unique_school_ids(cls, values):
        return _validate_positive_ids(values)


class ClassWithSectionUpdate(RequestModel):
    class_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    grade_level: Optional[str] = Field(default=None, max_length=50)
    sections: Optional[list[str]] = Field(default=None, min_length=1, max_length=100)

    @field_validator("class_name", "grade_level")
    @classmethod
    def strip_text(cls, value):
        return _clean_text(value) if value is not None else None

    @field_validator("sections")
    @classmethod
    def normalize_sections(cls, values):
        if values is None:
            return values
        cleaned = [_clean_text(v) for v in values]
        normalized = [v.upper() for v in cleaned]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Duplicate section names are not allowed.")
        if any(len(v) > 20 for v in normalized):
            raise ValueError("Section names cannot exceed 20 characters.")
        return normalized


class TopicCreate(RequestModel):
    topic_name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None

    @field_validator("topic_name")
    @classmethod
    def strip_name(cls, value):
        return _clean_text(value)


class ChapterCreate(RequestModel):
    chapter_name: str = Field(min_length=1, max_length=255)
    topics: list[TopicCreate] = Field(default_factory=list, max_length=500)

    @field_validator("chapter_name")
    @classmethod
    def strip_name(cls, value):
        return _clean_text(value)

    @model_validator(mode="after")
    def validate_unique_topic_names(self):
        names = [topic.topic_name.casefold() for topic in self.topics]
        if len(names) != len(set(names)):
            raise ValueError("Topic names must be unique within a chapter.")
        return self


class SubjectCreate(RequestModel):
    name: str = Field(min_length=1, max_length=100)
    class_ids: list[int] = Field(default_factory=list)
    chapters: list[ChapterCreate] = Field(default_factory=list, max_length=500)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value):
        return _clean_text(value)

    @field_validator("class_ids")
    @classmethod
    def unique_ids(cls, value):
        return _validate_positive_ids(value)

    @model_validator(mode="after")
    def validate_unique_chapter_names(self):
        names = [chapter.chapter_name.casefold() for chapter in self.chapters]
        if len(names) != len(set(names)):
            raise ValueError("Chapter names must be unique within a subject.")
        return self


class SubjectUpdate(RequestModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    class_ids: Optional[list[int]] = None
    chapters: Optional[list[ChapterCreate]] = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value):
        return _clean_text(value) if value is not None else None

    @field_validator("class_ids")
    @classmethod
    def unique_ids(cls, value):
        return _validate_positive_ids(value) if value is not None else value

    @model_validator(mode="after")
    def validate_unique_chapter_names(self):
        if self.chapters is None:
            return self
        names = [chapter.chapter_name.casefold() for chapter in self.chapters]
        if len(names) != len(set(names)):
            raise ValueError("Chapter names must be unique within a subject.")
        return self


class StudentCreate(RequestModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    gender: Optional[GenderEnum] = None
    dob: Optional[date] = None
    phone_number: Optional[str] = Field(default=None, pattern=r"^\d{10}$")
    school_id: int = Field(gt=0)
    class_id: Optional[int] = Field(default=None, gt=0)
    section_id: Optional[int] = Field(default=None, gt=0)
    parents_name: Optional[str] = Field(default=None, max_length=255)
    parents_ph_no: Optional[str] = Field(default=None, pattern=r"^\d{10}$")
    parents_email: Optional[EmailStr] = None

    @field_validator("name", "parents_name")
    @classmethod
    def strip_text(cls, value):
        return _clean_text(value) if value is not None else None

    @field_validator("email", "parents_email")
    @classmethod
    def normalize_email(cls, value):
        return _clean_email(value) if value is not None else None

    @model_validator(mode="after")
    def validate_dob(self):
        if self.dob and self.dob > date.today():
            raise ValueError("Date of birth cannot be in the future.")
        return self


class StudentUpdate(RequestModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    gender: Optional[GenderEnum] = None
    dob: Optional[date] = None
    phone_number: Optional[str] = Field(default=None, pattern=r"^\d{10}$")
    class_id: Optional[int] = Field(default=None, gt=0)
    section_id: Optional[int] = Field(default=None, gt=0)
    parents_name: Optional[str] = Field(default=None, max_length=255)
    parents_ph_no: Optional[str] = Field(default=None, pattern=r"^\d{10}$")
    parents_email: Optional[EmailStr] = None

    @field_validator("name", "parents_name")
    @classmethod
    def strip_text(cls, value):
        return _clean_text(value) if value is not None else None

    @field_validator("email", "parents_email")
    @classmethod
    def normalize_email(cls, value):
        return _clean_email(value) if value is not None else None

    @model_validator(mode="after")
    def validate_dob(self):
        if self.dob and self.dob > date.today():
            raise ValueError("Date of birth cannot be in the future.")
        return self


class ClassroomOperatorCreate(RequestModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone_number: Optional[str] = Field(default=None, pattern=r"^\d{10}$")
    gender: Optional[GenderEnum] = None
    school_id: int = Field(gt=0)
    class_ids: list[int] = Field(default_factory=list)
    activation_status: ActivationStatus = ActivationStatus.ACTIVE

    @field_validator("name")
    @classmethod
    def strip_name(cls, value):
        return _clean_text(value)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return _clean_email(value)

    @field_validator("class_ids")
    @classmethod
    def unique_ids(cls, value):
        return _validate_positive_ids(value)


class ClassroomOperatorAssignmentUpdate(RequestModel):
    class_ids: list[int] = Field(default_factory=list)

    @field_validator("class_ids")
    @classmethod
    def unique_ids(cls, value):
        return _validate_positive_ids(value)


# ---------------------------------------------------------------------------
# 1. School CRUD and school-admin assignment
# ---------------------------------------------------------------------------

@router.post("/schools", status_code=status.HTTP_201_CREATED, dependencies=[verify_super_admin])
def add_school(data: SchoolCreate, db: Session = Depends(get_db)):
    if db.query(School).filter(School.school_code == data.school_code).first():
        raise HTTPException(status_code=409, detail="School code already exists.")
    admins = _get_school_admins(db, data.school_admin_ids)
    classes = _get_school_classes(db, data.class_ids)

    school = School(
        name=data.name,
        school_code=data.school_code,
        state=data.state,
        distc=data.district,
        region=data.region,
        school_ph_no=data.school_ph_no,
        address=data.address,
        activation=data.activation,
    )
    school.school_admins = admins
    db.add(school)
    try:
        db.flush()
        db.execute(
            school_classes.insert(),
            [{"school_id": school.id, "class_id": class_obj.id} for class_obj in classes],
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="School code or class assignment conflicts with existing data.",
        ) from exc
    _commit(db, "School code or school-admin assignment conflicts with existing data.")
    db.refresh(school)
    return {"message": "School created successfully.", "school_id": school.id,
            "assigned_admin_ids": [admin.id for admin in school.school_admins],
            "assigned_classes": _format_school_classes(classes)}


@router.get("/schools", dependencies=[verify_super_admin])
def get_schools(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    schools = (
        db.query(School)
        .options(selectinload(School.school_admins))
        .order_by(School.id)
        .offset(skip).limit(limit).all()
    )
    school_ids = [school.id for school in schools]
    school_class_assignments: dict[int, list[ClassModel]] = {
        school_id: [] for school_id in school_ids
    }
    if school_ids:
        assignments = (
            db.query(school_classes.c.school_id, ClassModel)
            .join(ClassModel, school_classes.c.class_id == ClassModel.id)
            .options(selectinload(ClassModel.sections))
            .filter(school_classes.c.school_id.in_(school_ids))
            .order_by(school_classes.c.school_id, ClassModel.id)
            .all()
        )
        for school_id, class_obj in assignments:
            school_class_assignments[school_id].append(class_obj)
    return [{
        "school_id": s.id,
        "school_name": s.name,
        "school_code": s.school_code,
        "phone": s.school_ph_no,
        "district": s.distc,
        "state": s.state,
        "region": s.region,
        "school_admins": [
            {"admin_id": admin.id, "name": admin.name, "email": admin.email}
            for admin in s.school_admins
        ],
        "assigned_classes": _format_school_classes(school_class_assignments[s.id]),
        "status": s.activation.value if hasattr(s.activation, "value") else s.activation,
    } for s in schools]


@router.put("/schools/{school_id}", dependencies=[verify_super_admin])
def edit_school(school_id: int, data: SchoolUpdate, db: Session = Depends(get_db)):
    _require_nonempty_update(data)
    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found.")

    values = data.model_dump(exclude_unset=True)
    if "name" in values and values["name"] is None:
        raise HTTPException(status_code=422, detail="School name cannot be null.")
    if "school_code" in values and values["school_code"] is None:
        raise HTTPException(status_code=422, detail="School code cannot be null.")
    if "school_code" in values and db.query(School).filter(
        School.school_code == values["school_code"], School.id != school_id
    ).first():
        raise HTTPException(status_code=409, detail="School code already exists.")

    mapping = {"district": "distc"}
    for key, value in values.items():
        setattr(school, mapping.get(key, key), value)
    _commit(db, "School update conflicts with existing data.")
    return {"message": "School updated successfully."}


@router.put("/schools/{school_id}/assign-admins", dependencies=[verify_super_admin])
def assign_school_admins(school_id: int, data: SchoolAssignmentUpdate, db: Session = Depends(get_db)):
    school = db.query(School).options(selectinload(School.school_admins)).filter(
        School.id == school_id
    ).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found.")

    admins = _get_school_admins(db, data.admin_ids)
    school.school_admins = admins  # Replaces the complete assignment list.
    _commit(db, "School-admin assignment could not be saved.")
    return {
        "message": "School-admin assignments updated successfully.",
        "school_id": school.id,
        "assigned_admin_ids": [admin.id for admin in school.school_admins],
    }


@router.delete("/schools/{school_id}", dependencies=[verify_super_admin])
def delete_school(school_id: int, db: Session = Depends(get_db)):
    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found.")

    has_teachers = db.query(Teacher.id).filter(Teacher.school_id == school_id).first()
    has_students = db.query(Student.id).filter(Student.school_id == school_id).first()
    has_operators = db.query(ClassroomOperator.id).filter(ClassroomOperator.school_id == school_id).first()
    if has_teachers or has_students or has_operators:
        raise HTTPException(
            status_code=409,
            detail="School has teachers, students, or operators. Deactivate it or reassign/remove those records first."
        )
    db.delete(school)
    _commit(db, "School cannot be deleted because it is referenced by other records.")
    return {"message": "School deleted successfully."}


# ---------------------------------------------------------------------------
# 2. School-admin CRUD
# ---------------------------------------------------------------------------

@router.post("/school-admins", status_code=status.HTTP_201_CREATED, dependencies=[verify_super_admin])
def add_school_admin(data: SchoolAdminCreate, db: Session = Depends(get_db)):
    if db.query(User.id).filter(func.lower(User.email) == data.email).first():
        raise HTTPException(status_code=409, detail="Email already registered.")
    temporary_password = _generate_temporary_password()
    admin = User(
        name=data.name,
        email=data.email,
        password=hash_password(temporary_password),
        phone_number=data.phone_number,
        gender=data.gender,
        role=RoleEnum.SCHOOL_ADMIN,
        activation_status=data.activation_status,
    )
    db.add(admin)
    _commit(db, "Email already registered.")
    db.refresh(admin)
    return {
        "message": "School Admin user created successfully. Save the temporary password now; it will not be shown again.",
        "admin_id": admin.id,
        "temporary_password": temporary_password,
    }


@router.get("/school-admins", dependencies=[verify_super_admin])
def get_school_admins(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    admins = (
        db.query(User)
        .options(selectinload(User.administered_schools))
        .filter(User.role == RoleEnum.SCHOOL_ADMIN)
        .order_by(User.id).offset(skip).limit(limit).all()
    )
    return [{
        "admin_id": admin.id,
        "name": admin.name,
        "email": admin.email,
        "role": admin.role.value if hasattr(admin.role, "value") else admin.role,
        "list_of_schools": [
            {"school_id": s.id, "school_name": s.name, "school_code": s.school_code}
            for s in admin.administered_schools
        ],
        "status": admin.activation_status.value if hasattr(admin.activation_status, "value") else admin.activation_status,
    } for admin in admins]


@router.put("/school-admins/{admin_id}", dependencies=[verify_super_admin])
def edit_school_admin(admin_id: int, data: SchoolAdminUpdate, db: Session = Depends(get_db)):
    _require_nonempty_update(data)
    admin = _get_school_admin(db, admin_id)
    values = data.model_dump(exclude_unset=True)
    if "name" in values and values["name"] is None:
        raise HTTPException(status_code=422, detail="Name cannot be null.")
    if "email" in values:
        if values["email"] is None:
            raise HTTPException(status_code=422, detail="Email cannot be null.")
        if db.query(User.id).filter(func.lower(User.email) == values["email"], User.id != admin_id).first():
            raise HTTPException(status_code=409, detail="Email already registered.")
    for key, value in values.items():
        setattr(admin, key, value)
    _commit(db, "School Admin update conflicts with existing data.")
    return {"message": "School Admin updated successfully."}


@router.delete("/school-admins/{admin_id}", dependencies=[verify_super_admin])
def delete_school_admin(admin_id: int, db: Session = Depends(get_db)):
    admin = _get_school_admin(db, admin_id)
    db.delete(admin)
    _commit(db, "School Admin cannot be deleted while referenced.")
    return {"message": "School Admin deleted successfully."}


# ---------------------------------------------------------------------------
# 2a. Content-admin CRUD (global users; no school/class assignment)
# ---------------------------------------------------------------------------

def _get_content_admin(db: Session, admin_id: int) -> User:
    admin = db.query(User).filter(
        User.id == admin_id,
        User.role == RoleEnum.CONTENT_ADMIN,
    ).first()
    if admin is None:
        raise HTTPException(status_code=404, detail="Content Admin not found.")
    return admin


@router.post(
    "/content-admins",
    status_code=status.HTTP_201_CREATED,
    dependencies=[verify_super_admin],
)
def add_content_admin(data: ContentAdminCreate, db: Session = Depends(get_db)):
    if db.query(User.id).filter(func.lower(User.email) == data.email).first():
        raise HTTPException(status_code=409, detail="Email already registered.")

    temporary_password = _generate_temporary_password()
    admin = User(
        name=data.name,
        email=data.email,
        password=hash_password(temporary_password),
        phone_number=data.phone_number,
        gender=data.gender,
        role=RoleEnum.CONTENT_ADMIN,
        activation_status=data.activation_status,
    )
    db.add(admin)
    _commit(db, "Content Admin email already exists.")
    db.refresh(admin)
    return {
        "message": "Content Admin created successfully. Save the temporary password now; it will not be shown again.",
        "content_admin_id": admin.id,
        "temporary_password": temporary_password,
    }


@router.get("/content-admins", dependencies=[verify_super_admin])
def get_content_admins(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    admins = (
        db.query(User)
        .filter(User.role == RoleEnum.CONTENT_ADMIN)
        .order_by(User.id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [{
        "content_admin_id": admin.id,
        "name": admin.name,
        "email": admin.email,
        "phone_number": admin.phone_number,
        "gender": admin.gender.value if hasattr(admin.gender, "value") else admin.gender,
        "role": admin.role.value if hasattr(admin.role, "value") else admin.role,
        "activation_status": (
            admin.activation_status.value
            if hasattr(admin.activation_status, "value")
            else admin.activation_status
        ),
    } for admin in admins]


@router.put("/content-admins/{admin_id}", dependencies=[verify_super_admin])
def edit_content_admin(
    admin_id: int,
    data: ContentAdminUpdate,
    db: Session = Depends(get_db),
):
    _require_nonempty_update(data)
    admin = _get_content_admin(db, admin_id)
    values = data.model_dump(exclude_unset=True)

    if "name" in values and values["name"] is None:
        raise HTTPException(status_code=422, detail="Name cannot be null.")
    if "email" in values:
        if values["email"] is None:
            raise HTTPException(status_code=422, detail="Email cannot be null.")
        if db.query(User.id).filter(
            func.lower(User.email) == values["email"],
            User.id != admin_id,
        ).first():
            raise HTTPException(status_code=409, detail="Email already registered.")

    for key, value in values.items():
        setattr(admin, key, value)
    _commit(db, "Content Admin update conflicts with existing data.")
    return {"message": "Content Admin updated successfully."}


@router.delete("/content-admins/{admin_id}", dependencies=[verify_super_admin])
def delete_content_admin(admin_id: int, db: Session = Depends(get_db)):
    admin = _get_content_admin(db, admin_id)
    has_question_sets = db.query(QuestionSet.id).filter(
        QuestionSet.created_by == admin_id
    ).first()
    if has_question_sets:
        raise HTTPException(
            status_code=409,
            detail="Content Admin has created question sets and cannot be deleted. Deactivate the account instead.",
        )
    db.delete(admin)
    _commit(db, "Content Admin cannot be deleted while referenced.")
    return {"message": "Content Admin deleted successfully."}


# ---------------------------------------------------------------------------
# 3. Global classes and sections
# ---------------------------------------------------------------------------

@router.post("/classes-with-sections", status_code=status.HTTP_201_CREATED, dependencies=[verify_super_admin])
def add_class_with_sections(data: ClassWithSectionCreate, db: Session = Depends(get_db)):
    schools = _get_many(db, School, data.school_ids, "school")
    class_obj = db.query(ClassModel).filter(
        func.lower(ClassModel.class_name) == data.class_name.lower()
    ).first()
    if class_obj is None:
        class_obj = ClassModel(class_name=data.class_name, grade_level=data.grade_level)
        db.add(class_obj)
        db.flush()
    elif data.grade_level is not None:
        class_obj.grade_level = data.grade_level

    existing = {s.section_name.lower() for s in class_obj.sections}
    added = []
    for name in data.sections:
        if name.lower() not in existing:
            db.add(ClassSection(class_id=class_obj.id, section_name=name))
            added.append(name)
    existing_school_ids = {
        row[0]
        for row in db.query(school_classes.c.school_id).filter(
            school_classes.c.class_id == class_obj.id
        ).all()
    }
    new_links = [
        {"school_id": school.id, "class_id": class_obj.id}
        for school in schools
        if school.id not in existing_school_ids
    ]
    if new_links:
        db.execute(school_classes.insert(), new_links)
    _commit(db, "Class or section already exists.")
    return {
        "message": "Global class configured successfully.",
        "class_id": class_obj.id,
        "added_sections": added,
        "school_ids": sorted(existing_school_ids | {school.id for school in schools}),
    }


@router.get("/classes-with-sections", dependencies=[verify_super_admin])
def get_classes_summary(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    classes = (
        db.query(ClassModel)
        .options(selectinload(ClassModel.sections))
        .order_by(ClassModel.id).offset(skip).limit(limit).all()
    )
    return [{
        "class_id": c.id,
        "class_name": c.class_name,
        "grade_level": c.grade_level,
        "total_sections": len(c.sections),
        "sections": [{"section_id": s.id, "section_name": s.section_name} for s in c.sections],
    } for c in classes]


@router.put("/classes-with-sections/{class_id}", dependencies=[verify_super_admin])
def edit_class(class_id: int, data: ClassWithSectionUpdate, db: Session = Depends(get_db)):
    _require_nonempty_update(data)
    class_obj = _get_class(db, class_id)
    values = data.model_dump(exclude_unset=True)

    if "class_name" in values:
        if values["class_name"] is None:
            raise HTTPException(status_code=422, detail="class_name cannot be null.")
        duplicate = db.query(ClassModel.id).filter(
            func.lower(ClassModel.class_name) == values["class_name"].lower(),
            ClassModel.id != class_id
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="Class name already exists.")
        class_obj.class_name = values["class_name"]

    if "grade_level" in values:
        class_obj.grade_level = values["grade_level"]

    if "sections" in values:
        requested = set(values["sections"])
        existing = {s.section_name: s for s in class_obj.sections}
        removed = set(existing) - requested
        if removed:
            removed_section_ids = [existing[n].id for n in removed]
            in_use = db.query(Student.id).filter(
                (Student.class_id == class_id) | (Student.section_id.in_(removed_section_ids))
            ).first()
            teacher_in_use = (
                db.query(Teacher.id)
                .join(Teacher.sections)
                .filter(ClassSection.id.in_(removed_section_ids))
                .first()
            )
            lesson_in_use = db.query(TeacherLessonContent.id).filter(
                TeacherLessonContent.section_id.in_(removed_section_ids)
            ).first()
            shared_in_use = db.query(TeacherLessonShare.id).filter(
                TeacherLessonShare.section_id.in_(removed_section_ids),
                TeacherLessonShare.revoked_at.is_(None),
            ).first()
            quiz_in_use = db.query(QuestionSet.id).filter(
                QuestionSet.section_id.in_(removed_section_ids)
            ).first()
            if in_use or teacher_in_use or lesson_in_use or shared_in_use or quiz_in_use:
                raise HTTPException(
                    status_code=409,
                    detail="One or more sections being removed are assigned to students or teachers, or have lesson content/access or quizzes."
                )
        for name in requested - set(existing):
            db.add(ClassSection(class_id=class_id, section_name=name))
        for name in removed:
            db.delete(existing[name])

    _commit(db, "Class update conflicts with existing data.")
    return {"message": "Global class updated successfully."}


@router.delete("/classes-with-sections/{class_id}", dependencies=[verify_super_admin])
def delete_class(class_id: int, db: Session = Depends(get_db)):
    class_obj = _get_class(db, class_id)
    section_ids = [s.id for s in class_obj.sections]
    
    student_exists = db.query(Student.id).filter(
        (Student.class_id == class_id) | (Student.section_id.in_(section_ids) if section_ids else False)
    ).first()
    teacher_exists = db.query(Teacher.id).join(Teacher.classes).filter(ClassModel.id == class_id).first()
    subject_exists = db.query(Subject.id).join(Subject.classes).filter(ClassModel.id == class_id).first()
    operator_exists = db.query(ClassroomOperatorAssignment.id).filter(ClassroomOperatorAssignment.class_id == class_id).first()
    lesson_exists = db.query(TeacherLessonContent.id).filter(
        TeacherLessonContent.class_id == class_id
    ).first()
    quiz_exists = db.query(QuestionSet.id).filter(
        QuestionSet.class_id == class_id
    ).first()
    shared_lesson_exists = (
        db.query(TeacherLessonShare.id)
        .join(ClassSection, ClassSection.id == TeacherLessonShare.section_id)
        .filter(
            ClassSection.class_id == class_id,
            TeacherLessonShare.revoked_at.is_(None),
        )
        .first()
    )

    if student_exists or teacher_exists or subject_exists or operator_exists or lesson_exists or shared_lesson_exists or quiz_exists:
        raise HTTPException(
            status_code=409,
            detail="Class is referenced by students, teachers, subjects, classroom operators, lesson content/access, or quizzes. Remove those records before deleting this global class."
        )
    db.delete(class_obj)
    _commit(db, "Class cannot be deleted because it is referenced.")
    return {"message": "Global class deleted successfully."}


# ---------------------------------------------------------------------------
# 4. Global subjects, chapters and topics
# ---------------------------------------------------------------------------

def _replace_chapters(db: Session, subject: Subject, chapters: list) -> None:
    chapter_ids = [chapter.id for chapter in subject.chapters]
    if chapter_ids and db.query(TeacherLessonContent.id).filter(
        TeacherLessonContent.chapter_id.in_(chapter_ids)
    ).first():
        raise HTTPException(
            status_code=409,
            detail="Subject chapters cannot be replaced while lesson content references them.",
        )
    for chapter in list(subject.chapters):
        db.delete(chapter)
    db.flush()
    subject.chapters.clear()

    for chapter_data in chapters:
        if isinstance(chapter_data, dict):
            chapter_name = chapter_data.get("chapter_name")
            topics = chapter_data.get("topics", [])
        else:
            chapter_name = chapter_data.chapter_name
            topics = chapter_data.topics

        chapter = Chapter(chapter_name=chapter_name)
        for topic_data in topics:
            if isinstance(topic_data, dict):
                topic_name = topic_data.get("topic_name")
                description = topic_data.get("description")
            else:
                topic_name = topic_data.topic_name
                description = topic_data.description

            chapter.topics.append(Topic(
                topic_name=topic_name,
                description=description,
            ))
        subject.chapters.append(chapter)


@router.post("/subjects", status_code=status.HTTP_201_CREATED, dependencies=[verify_super_admin])
def add_subject(data: SubjectCreate, db: Session = Depends(get_db)):
    classes = _get_many(db, ClassModel, data.class_ids, "class")
    duplicate = db.query(Subject.id).filter(Subject.name == data.name).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="A global subject with this name already exists.")

    subject = Subject(name=data.name)
    subject.classes = classes
    _replace_chapters(db, subject, data.chapters)
    db.add(subject)
    _commit(db, "Subject name or associations conflict with existing data.")
    db.refresh(subject)
    return {"message": "Global subject created successfully.", "subject_id": subject.id}


@router.get("/subjects", dependencies=[verify_super_admin])
def get_subjects(
    class_id: Optional[int] = Query(default=None, gt=0),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(Subject).options(
        selectinload(Subject.chapters).selectinload(Chapter.topics),
        selectinload(Subject.classes),
    )
    if class_id is not None:
        _get_class(db, class_id)
        query = query.join(Subject.classes).filter(ClassModel.id == class_id)
    subjects = query.order_by(Subject.id).offset(skip).limit(limit).all()

    return [{
        "subject_id": subject.id,
        "subject_name": subject.name,
        "class_ids": [c.id for c in subject.classes],
        "classes": [{"class_id": c.id, "class_name": c.class_name} for c in subject.classes],
        "total_chapters": len(subject.chapters),
        "chapters": [{
            "chapter_id": chapter.id,
            "chapter_name": chapter.chapter_name,
            "total_topics": len(chapter.topics),
            "topics": [{
                "topic_id": topic.id,
                "topic_name": topic.topic_name,
                "description": topic.description,
            } for topic in chapter.topics],
        } for chapter in subject.chapters],
    } for subject in subjects]


@router.put("/subjects/{subject_id}", dependencies=[verify_super_admin])
def edit_subject(subject_id: int, data: SubjectUpdate, db: Session = Depends(get_db)):
    _require_nonempty_update(data)
    subject = db.query(Subject).options(
        selectinload(Subject.chapters).selectinload(Chapter.topics),
        selectinload(Subject.classes),
        selectinload(Subject.teachers).selectinload(Teacher.classes),
    ).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found.")

    values = data.model_dump(exclude_unset=True)
    if "name" in values:
        if values["name"] is None:
            raise HTTPException(status_code=422, detail="Subject name cannot be null.")
        duplicate = db.query(Subject.id).filter(
            Subject.name == values["name"], Subject.id != subject_id
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="A global subject with this name already exists.")
        subject.name = values["name"]

    if "class_ids" in values:
        if values["class_ids"] is None:
            raise HTTPException(status_code=422, detail="class_ids cannot be null; use an empty list to clear mappings.")
        updated_classes = _get_many(db, ClassModel, values["class_ids"], "class")
        proposed_class_ids = set(values["class_ids"])
        removed_class_ids = {
            class_obj.id for class_obj in subject.classes
        } - proposed_class_ids
        if removed_class_ids and db.query(TeacherLessonContent.id).filter(
            TeacherLessonContent.subject_id == subject.id,
            TeacherLessonContent.class_id.in_(removed_class_ids),
        ).first():
            raise HTTPException(
                status_code=409,
                detail="Subject class mappings cannot be removed while lesson content uses them.",
            )
        teachers_without_assigned_class = [
            teacher.id
            for teacher in subject.teachers
            if not proposed_class_ids.intersection(
                class_obj.id for class_obj in teacher.classes
            )
        ]
        if teachers_without_assigned_class:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Subject classes cannot be changed because the update would leave "
                    f"teachers without a matching assigned class: {teachers_without_assigned_class}"
                ),
            )
        subject.classes = updated_classes

    if "chapters" in values:
        if values["chapters"] is None:
            raise HTTPException(status_code=422, detail="chapters cannot be null; use an empty list to clear chapters.")
        _replace_chapters(db, subject, values["chapters"])

    _commit(db, "Subject update conflicts with existing data.")
    return {"message": "Global subject updated successfully."}


@router.delete("/subjects/{subject_id}", dependencies=[verify_super_admin])
def delete_subject(subject_id: int, db: Session = Depends(get_db)):
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found.")
    if db.query(TeacherLessonContent.id).filter(
        TeacherLessonContent.subject_id == subject_id
    ).first():
        raise HTTPException(
            status_code=409,
            detail="Subject cannot be deleted while lesson content references it.",
        )
    db.delete(subject)
    _commit(db, "Subject cannot be deleted because it is referenced by other records.")
    return {"message": "Global subject and its chapters/topics deleted successfully."}


# ---------------------------------------------------------------------------
# 5. Teacher CRUD and global class/subject assignments
# ---------------------------------------------------------------------------

@router.post("/teachers", status_code=status.HTTP_201_CREATED, dependencies=[verify_super_admin])
def add_teacher(data: TeacherCreate, db: Session = Depends(get_db)):
    school = db.query(School).filter(School.id == data.school_id).first()
    if school is None:
        raise HTTPException(status_code=404, detail="School not found.")
    _verify_school_active(school)

    if db.query(User.id).filter(func.lower(User.email) == data.email).first():
        raise HTTPException(status_code=409, detail="Email already registered.")

    classes = _require_school_classes(db, school.id, data.class_ids)
    sections = _validate_teacher_sections(db, data.class_ids, data.section_ids)
    subjects = _validate_teacher_subjects(db, data.class_ids, data.subject_ids)

    user = User(
        name=data.name,
        email=data.email,
        password=hash_password(data.password),
        phone_number=data.phone_number,
        gender=data.gender,
        role=RoleEnum.TEACHER,
        activation_status=data.activation_status,
    )
    teacher = Teacher(school_id=data.school_id, qualification=data.qualification)
    teacher.classes = classes
    teacher.sections = sections
    teacher.subjects = subjects
    user.teacher_profile = teacher
    db.add(user)
    db.query(School).filter(School.id == data.school_id).update(
        {School.total_teacher: School.total_teacher + 1},
        synchronize_session=False,
    )
    _commit(db, "Teacher email or assignment conflicts with existing data.")
    db.refresh(teacher)
    return {"message": "Teacher created successfully.", "teacher_id": teacher.id, "user_id": user.id}


@router.put("/teachers/{teacher_id}/assign-classes-subjects", dependencies=[verify_super_admin])
def assign_teacher_classes_and_subjects(
    teacher_id: int,
    data: TeacherAssignmentUpdate,
    db: Session = Depends(get_db),
):
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found.")
    school = db.query(School).filter(School.id == teacher.school_id).first()
    if school is None:
        raise HTTPException(status_code=404, detail="Teacher's school not found.")
    _verify_school_active(school)

    classes = _require_school_classes(db, school.id, data.class_ids)
    sections = _validate_teacher_sections(db, data.class_ids, data.section_ids)
    subjects = _validate_teacher_subjects(db, data.class_ids, data.subject_ids)
    teacher.classes = classes
    teacher.sections = sections
    teacher.subjects = subjects
    _commit(db, "Teacher assignments could not be saved.")
    return {"message": "Teacher assignments updated successfully.", "teacher_id": teacher.id}


@router.get("/teachers", dependencies=[verify_super_admin])
def get_teachers(
    school_id: Optional[int] = Query(default=None, gt=0),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(Teacher).options(
        selectinload(Teacher.user),
        selectinload(Teacher.school),
        selectinload(Teacher.classes),
        selectinload(Teacher.sections).selectinload(ClassSection.class_obj),
        selectinload(Teacher.subjects),
    )
    if school_id is not None:
        query = query.filter(Teacher.school_id == school_id)
    teachers = query.order_by(Teacher.id).offset(skip).limit(limit).all()

    return [{
        "teacher_id": teacher.id,
        "user_id": teacher.user.id if teacher.user else None,
        "username": teacher.user.name if teacher.user else None,
        "school_id": teacher.school_id,
        "school_name": teacher.school.name if teacher.school else None,
        "email": teacher.user.email if teacher.user else None,
        "phone": teacher.user.phone_number if teacher.user else None,
        "qualification": teacher.qualification,
        "assigned_classes": [
            {"class_id": c.id, "class_name": c.class_name} for c in teacher.classes
        ],
        "assigned_sections": [
            {
                "section_id": section.id,
                "section_name": section.section_name,
                "class_id": section.class_id,
                "class_name": section.class_obj.class_name if section.class_obj else None,
            }
            for section in teacher.sections
        ],
        "assigned_subjects": [
            {"subject_id": s.id, "subject_name": s.name} for s in teacher.subjects
        ],
        "status": (
            teacher.user.activation_status.value
            if teacher.user and hasattr(teacher.user.activation_status, "value")
            else (teacher.user.activation_status if teacher.user else None)
        ),
    } for teacher in teachers]


@router.put("/teachers/{teacher_id}", dependencies=[verify_super_admin])
def edit_teacher(teacher_id: int, data: TeacherUpdate, db: Session = Depends(get_db)):
    _require_nonempty_update(data)
    teacher = db.query(Teacher).options(selectinload(Teacher.user)).filter(
        Teacher.id == teacher_id
    ).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found.")
    if teacher.user is None:
        raise HTTPException(status_code=409, detail="Teacher has no linked user account.")

    values = data.model_dump(exclude_unset=True)
    if "email" in values:
        if values["email"] is None:
            raise HTTPException(status_code=422, detail="Email cannot be null.")
        duplicate = db.query(User.id).filter(
            func.lower(User.email) == values["email"], User.id != teacher.user.id
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="Email already registered.")

    if "name" in values and values["name"] is None:
        raise HTTPException(status_code=422, detail="Name cannot be null.")
    user_fields = {"name", "email", "phone_number", "gender", "activation_status"}
    teacher_fields = {"qualification"}
    for key, value in values.items():
        if key in user_fields:
            setattr(teacher.user, key, value)
        elif key in teacher_fields:
            setattr(teacher, key, value)

    _commit(db, "Teacher update conflicts with existing data.")
    return {"message": "Teacher updated successfully."}


@router.delete("/teachers/{teacher_id}", dependencies=[verify_super_admin])
def delete_teacher(teacher_id: int, db: Session = Depends(get_db)):
    teacher = db.query(Teacher).options(selectinload(Teacher.user)).filter(
        Teacher.id == teacher_id
    ).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found.")
    if teacher.user is not None:
        db.delete(teacher.user)
    else:
        db.delete(teacher)
    _commit(db, "Teacher cannot be deleted because it is referenced by other records.")
    return {"message": "Teacher and linked user account deleted successfully."}


# ---------------------------------------------------------------------------
# 6. Student profile CRUD
# ---------------------------------------------------------------------------

@router.post("/students", status_code=status.HTTP_201_CREATED, dependencies=[verify_super_admin])
def add_student(data: StudentCreate, db: Session = Depends(get_db)):
    school = db.query(School).filter(School.id == data.school_id).first()
    if school is None:
        raise HTTPException(status_code=404, detail="School not found.")
    _verify_school_active(school)

    if db.query(Student.id).filter(func.lower(Student.email) == data.email).first():
        raise HTTPException(status_code=409, detail="Student email already exists.")
    _validate_student_placement(db, school.id, data.class_id, data.section_id)

    student = Student(**data.model_dump())
    db.add(student)
    db.query(School).filter(School.id == data.school_id).update(
        {School.total_student: School.total_student + 1},
        synchronize_session=False,
    )
    _commit(db, "Student email or parent email already exists.")
    db.refresh(student)
    return {"message": "Student profile created successfully.", "student_id": student.id}


@router.get("/students", dependencies=[verify_super_admin])
def get_students(
    school_id: Optional[int] = Query(default=None, gt=0),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(Student).options(
        selectinload(Student.school),
        selectinload(Student.class_obj),
        selectinload(Student.section_obj),
    )
    if school_id is not None:
        query = query.filter(Student.school_id == school_id)
    students = query.order_by(Student.id).offset(skip).limit(limit).all()
    return [{
        "student_id": s.id,
        "name": s.name,
        "email": s.email,
        "gender": s.gender.value if hasattr(s.gender, "value") else s.gender,
        "dob": s.dob,
        "phone_number": s.phone_number,
        "school_id": s.school_id,
        "school_name": s.school.name if s.school else None,
        "class_id": s.class_id,
        "class_name": s.class_obj.class_name if s.class_obj else None,
        "section_id": s.section_id,
        "section_name": s.section_obj.section_name if s.section_obj else None,
        "parents_name": s.parents_name,
        "parents_ph_no": s.parents_ph_no,
        "parents_email": s.parents_email,
    } for s in students]


@router.put("/students/{student_id}", dependencies=[verify_super_admin])
def edit_student(student_id: int, data: StudentUpdate, db: Session = Depends(get_db)):
    _require_nonempty_update(data)
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    values = data.model_dump(exclude_unset=True)

    next_class_id = values.get("class_id", student.class_id)
    next_section_id = values.get("section_id", student.section_id)
    if "class_id" in values and "section_id" not in values and student.section_id is not None:
        old_section = db.query(ClassSection).filter(ClassSection.id == student.section_id).first()
        if old_section is None or old_section.class_id != next_class_id:
            next_section_id = None
            values["section_id"] = None
    _validate_student_placement(db, student.school_id, next_class_id, next_section_id)

    if "name" in values and values["name"] is None:
        raise HTTPException(status_code=422, detail="Name cannot be null.")
    if "email" in values and values["email"] is None:
        raise HTTPException(status_code=422, detail="Email cannot be null.")
    if "email" in values and values["email"] is not None:
        duplicate = db.query(Student.id).filter(
            func.lower(Student.email) == values["email"], Student.id != student_id
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="Student email already exists.")
    for key, value in values.items():
        setattr(student, key, value)
    _commit(db, "Student update conflicts with existing data.")
    return {"message": "Student updated successfully."}


@router.delete("/students/{student_id}", dependencies=[verify_super_admin])
def delete_student(student_id: int, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    affected_lesson_ids = {
        row[0]
        for row in db.query(TeacherLessonShare.lesson_id)
        .filter(
            TeacherLessonShare.student_id == student_id,
            TeacherLessonShare.revoked_at.is_(None),
        )
        .distinct()
        .all()
    }
    db.delete(student)
    db.flush()
    now = datetime.now(timezone.utc)
    for lesson_id in affected_lesson_ids:
        still_shared = db.query(TeacherLessonShare.id).filter(
            TeacherLessonShare.lesson_id == lesson_id,
            TeacherLessonShare.revoked_at.is_(None),
        ).first()
        lesson = db.query(TeacherLessonContent).filter(
            TeacherLessonContent.id == lesson_id
        ).first()
        if not still_shared and lesson and lesson.status == "shared":
            lesson.status = lesson.status_before_share or "done"
            lesson.status_before_share = None
            lesson.updated_at = now
    _commit(db, "Student cannot be deleted because it is referenced by other records.")
    return {"message": "Student profile deleted successfully."}


# ---------------------------------------------------------------------------
# 7. Classroom Operator CRUD
# ---------------------------------------------------------------------------

@router.post("/classroom-operators", status_code=status.HTTP_201_CREATED, dependencies=[verify_super_admin])
def add_classroom_operator(data: ClassroomOperatorCreate, db: Session = Depends(get_db)):
    school = db.query(School).filter(School.id == data.school_id).first()
    if school is None:
        raise HTTPException(status_code=404, detail="School not found.")
    _verify_school_active(school)

    if db.query(User.id).filter(func.lower(User.email) == data.email).first():
        raise HTTPException(status_code=409, detail="Email already registered.")

    classes = _require_school_classes(db, school.id, data.class_ids)

    user = User(
        name=data.name,
        email=data.email,
        password=hash_password(data.password),
        phone_number=data.phone_number,
        gender=data.gender,
        role=RoleEnum.CLASSROOM_OPERATOR,
        activation_status=data.activation_status,
    )
    
    operator = ClassroomOperator(school_id=data.school_id)
    
    for cls in classes:
        operator.class_assignments.append(ClassroomOperatorAssignment(class_id=cls.id))

    user.operator_profile = operator
    db.add(user)
    _commit(db, "Classroom operator email or assignment conflicts with existing data.")
    db.refresh(operator)
    return {"message": "Classroom operator created successfully.", "operator_id": operator.id, "user_id": user.id}


@router.put("/classroom-operators/{operator_id}/assign-classes", dependencies=[verify_super_admin])
def assign_operator_classes(
    operator_id: int,
    data: ClassroomOperatorAssignmentUpdate,
    db: Session = Depends(get_db),
):
    operator = db.query(ClassroomOperator).filter(ClassroomOperator.id == operator_id).first()
    if not operator:
        raise HTTPException(status_code=404, detail="Classroom operator not found.")
    school = db.query(School).filter(School.id == operator.school_id).first()
    if school is None:
        raise HTTPException(status_code=404, detail="Classroom operator's school not found.")
    _verify_school_active(school)

    classes = _require_school_classes(db, school.id, data.class_ids)

    operator.class_assignments.clear()
    db.flush()

    for cls in classes:
        operator.class_assignments.append(ClassroomOperatorAssignment(class_id=cls.id))

    _commit(db, "Classroom operator class assignments could not be saved.")
    return {"message": "Classroom operator class assignments updated successfully.", "operator_id": operator.id}


@router.get("/classroom-operators", dependencies=[verify_super_admin])
def get_classroom_operators(
    school_id: Optional[int] = Query(default=None, gt=0),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(ClassroomOperator).options(
        selectinload(ClassroomOperator.user),
        selectinload(ClassroomOperator.school),
        selectinload(ClassroomOperator.class_assignments).selectinload(ClassroomOperatorAssignment.class_obj),
    )
    if school_id is not None:
        query = query.filter(ClassroomOperator.school_id == school_id)
    
    operators = query.order_by(ClassroomOperator.id).offset(skip).limit(limit).all()

    return [{
        "operator_id": op.id,
        "user_id": op.user.id if op.user else None,
        "name": op.user.name if op.user else None,
        "email": op.user.email if op.user else None,
        "phone": op.user.phone_number if op.user else None,
        "school_id": op.school_id,
        "school_name": op.school.name if op.school else None,
        "assigned_classes": [
            {"class_id": assignment.class_obj.id, "class_name": assignment.class_obj.class_name} 
            for assignment in op.class_assignments if assignment.class_obj
        ],
        "status": (
            op.user.activation_status.value
            if op.user and hasattr(op.user.activation_status, "value")
            else (op.user.activation_status if op.user else None)
        ),
    } for op in operators]


@router.delete("/classroom-operators/{operator_id}", dependencies=[verify_super_admin])
def delete_classroom_operator(operator_id: int, db: Session = Depends(get_db)):
    operator = db.query(ClassroomOperator).options(selectinload(ClassroomOperator.user)).filter(
        ClassroomOperator.id == operator_id
    ).first()
    if not operator:
        raise HTTPException(status_code=404, detail="Classroom operator not found.")
    
    if operator.user is not None:
        db.delete(operator.user)
    else:
        db.delete(operator)
        
    _commit(db, "Classroom operator cannot be deleted because it is referenced by other records.")
    return {"message": "Classroom operator and linked user account deleted successfully."}