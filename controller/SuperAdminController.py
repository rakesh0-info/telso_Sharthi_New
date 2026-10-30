from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date

from databaseCon import get_db
from databaseModel.userModel import User
from databaseModel.schoolModel import School
from databaseModel.classModel import ClassModel, ClassSection
from databaseModel.teacherModel import Teacher
from databaseModel.studentModel import Student
from databaseModel.classroomOperatorModel import ClassroomOperator
from databaseModel.subjectModel import Subject
from databaseModel.chapterModel import Chapter, Topic
from enums import RoleEnum, ActivationStatus, GenderEnum
from util_validate.password_security import hash_password
from pydantic import BaseModel, EmailStr, Field

from jwts.DB_Security_Config import require_roles

router = APIRouter(prefix="/api/super-admin", tags=["Super Admin Management"])

verify_super_admin = Depends(require_roles(RoleEnum.SUPER_ADMIN))


# ==========================================
# PYDANTIC SCHEMAS
# ==========================================

class SchoolCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    school_code: str = Field(..., min_length=2, max_length=50)
    state: Optional[str] = None
    district: Optional[str] = None
    school_ph_no: Optional[str] = Field(None, pattern=r"^\d{10}$")
    address: Optional[str] = None
    school_admin_ids: Optional[List[int]] = []
    activation: ActivationStatus = ActivationStatus.ACTIVE

class SchoolUpdate(BaseModel):
    name: Optional[str] = None
    school_code: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    school_ph_no: Optional[str] = Field(None, pattern=r"^\d{10}$")
    address: Optional[str] = None
    school_admin_ids: Optional[List[int]] = None
    activation: Optional[ActivationStatus] = None


class SchoolAdminCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=6)
    phone_number: Optional[str] = Field(None, pattern=r"^\d{10}$")
    gender: Optional[GenderEnum] = None
    activation_status: ActivationStatus = ActivationStatus.ACTIVE

class SchoolAdminUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = Field(None, pattern=r"^\d{10}$")
    gender: Optional[GenderEnum] = None
    activation_status: Optional[ActivationStatus] = None


class SchoolAssignmentUpdate(BaseModel):
    school_admin_id: Optional[int] = None


class TeacherCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=6)
    phone_number: Optional[str] = Field(None, pattern=r"^\d{10}$")
    gender: Optional[GenderEnum] = None
    school_id: int
    qualification: Optional[str] = None
    class_ids: Optional[List[int]] = []  # List of classes
    subject_ids: Optional[List[int]] = []  # List of subjects

class TeacherUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = Field(None, pattern=r"^\d{10}$")
    gender: Optional[GenderEnum] = None
    qualification: Optional[str] = None
    activation_status: Optional[ActivationStatus] = None

class TeacherAssignmentUpdate(BaseModel):
    class_ids: List[int] = Field(..., description="List of class IDs to assign/reassign")
    subject_ids: List[int] = Field(..., description="List of subject IDs to assign/reassign")


class OperatorCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=6)
    phone_number: Optional[str] = Field(None, pattern=r"^\d{10}$")
    gender: Optional[GenderEnum] = None
    school_id: int

class OperatorUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = Field(None, pattern=r"^\d{10}$")
    gender: Optional[GenderEnum] = None


class StudentCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    gender: Optional[GenderEnum] = None
    dob: Optional[date] = None
    phone_number: Optional[str] = Field(None, pattern=r"^\d{10}$")
    school_id: int
    class_id: Optional[int] = None
    section_id: Optional[int] = None
    parents_name: Optional[str] = None
    parents_ph_no: Optional[str] = Field(None, pattern=r"^\d{10}$")
    parents_email: Optional[EmailStr] = None

class StudentUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    gender: Optional[GenderEnum] = None
    dob: Optional[date] = None
    phone_number: Optional[str] = Field(None, pattern=r"^\d{10}$")
    class_id: Optional[int] = None
    section_id: Optional[int] = None
    parents_name: Optional[str] = None
    parents_ph_no: Optional[str] = Field(None, pattern=r"^\d{10}$")
    parents_email: Optional[EmailStr] = None


class ClassWithSectionCreate(BaseModel):
    class_name: str = Field(..., min_length=1)
    grade_level: Optional[str] = None
    sections: List[str] = Field(..., min_items=1)

class ClassWithSectionUpdate(BaseModel):
    class_name: Optional[str] = None
    grade_level: Optional[str] = None
    sections: Optional[List[str]] = None


class TopicCreate(BaseModel):
    topic_name: str = Field(..., min_length=1)
    description: Optional[str] = None

class ChapterCreate(BaseModel):
    chapter_name: str = Field(..., min_length=1)
    topics: List[TopicCreate] = Field(..., min_items=1)

class SubjectWithChaptersCreate(BaseModel):
    name: str = Field(..., min_length=1)
    class_id: int
    section_id: Optional[int] = None
    chapters: List[ChapterCreate] = Field(..., min_items=1)

class SubjectUpdate(BaseModel):
    name: Optional[str] = None
    class_id: Optional[int] = None
    section_id: Optional[int] = None
    chapters: Optional[List[ChapterCreate]] = None


# ==========================================
# 1. SCHOOL CRUD & ASSIGNMENT
# ==========================================
@router.post("/schools", status_code=status.HTTP_201_CREATED, dependencies=[verify_super_admin])
def add_school(data: SchoolCreate, db: Session = Depends(get_db)):
    if db.query(School).filter(School.school_code == data.school_code).first():
        raise HTTPException(status_code=400, detail="School with this code already exists.")
    
    admin_ids = data.school_admin_ids or []
    school_data = data.dict(exclude={"school_admin_ids"})

    new_school = School(**school_data)
    
    if admin_ids:
        admins = db.query(User).filter(User.id.in_(admin_ids), User.role == RoleEnum.SCHOOL_ADMIN).all()
        if len(admins) != len(admin_ids):
            raise HTTPException(status_code=404, detail="One or more specified School Admins not found or invalid role.")
        new_school.administered_schools = admins

    db.add(new_school)
    db.commit()
    db.refresh(new_school)
    return {"message": "School created successfully", "school_id": new_school.id}


@router.get("/schools", dependencies=[verify_super_admin])
def get_schools(db: Session = Depends(get_db)):
    schools = db.query(School).all()
    result = []
    for s in schools:
        admins_list = [
            {"admin_id": admin.id, "name": admin.name, "email": admin.email}
            for admin in getattr(s, "administered_schools", [])
        ]
        result.append({
            "school_id": s.id,
            "school_name": s.name,
            "school_code": s.school_code,
            "phone": s.school_ph_no,
            "district": s.distc,
            "state": s.state,
            "school_admins": admins_list,  
            "status": s.activation.value if hasattr(s.activation, "value") else s.activation
        })
    return result


@router.put("/schools/{school_id}", dependencies=[verify_super_admin])
def edit_school(school_id: int, data: SchoolUpdate, db: Session = Depends(get_db)):
    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found.")

    update_data = data.dict(exclude_unset=True)
    if "school_code" in update_data:
        if db.query(School).filter(School.school_code == update_data["school_code"], School.id != school_id).first():
            raise HTTPException(status_code=400, detail="School code already in use.")

    for key, value in update_data.items():
        setattr(school, key, value)

    db.commit()
    return {"message": "School updated successfully"}

@router.patch("/schools/{school_id}/assign-admin", dependencies=[verify_super_admin])
def assign_school_admin(school_id: int, data: SchoolAssignmentUpdate, db: Session = Depends(get_db)):
    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found.")

    if data.school_admin_id:
        admin = db.query(User).filter(User.id == data.school_admin_id, User.role == RoleEnum.SCHOOL_ADMIN).first()
        if not admin:
            raise HTTPException(status_code=404, detail="School Admin not found.")
        school.school_admin_id = data.school_admin_id
    else:
        school.school_admin_id = None

    db.commit()
    return {"message": "School assignment updated successfully"}

@router.delete("/schools/{school_id}", dependencies=[verify_super_admin])
def delete_school(school_id: int, db: Session = Depends(get_db)):
    school = db.query(School).filter(School.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found.")
    db.delete(school)
    db.commit()
    return {"message": "School deleted successfully."}


# ==========================================
# 2. SCHOOL ADMIN CRUD
# ==========================================

@router.post("/school-admins", status_code=status.HTTP_201_CREATED, dependencies=[verify_super_admin])
def add_school_admin(data: SchoolAdminCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered.")

    new_admin = User(
        name=data.name,
        email=data.email,
        password=hash_password(data.password),
        phone_number=data.phone_number,
        gender=data.gender,
        role=RoleEnum.SCHOOL_ADMIN,
        activation_status=data.activation_status
    )
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)
    return {"message": "School Admin created successfully", "admin_id": new_admin.id}

@router.get("/school-admins", dependencies=[verify_super_admin])
def get_school_admins(db: Session = Depends(get_db)):
    admins = db.query(User).filter(User.role == RoleEnum.SCHOOL_ADMIN).all()
    result = []
    for adm in admins:
        schools_list = [{"school_id": sch.id, "school_name": sch.name, "school_code": sch.school_code} for sch in adm.administered_schools]
        result.append({
            "admin_id": adm.id,
            "name": adm.name,
            "email": adm.email,
            "role": adm.role.value if hasattr(adm.role, "value") else adm.role,
            "list_of_schools": schools_list,
            "status": adm.activation_status.value if hasattr(adm.activation_status, "value") else adm.activation_status
        })
    return result

@router.put("/school-admins/{admin_id}", dependencies=[verify_super_admin])
def edit_school_admin(admin_id: int, data: SchoolAdminUpdate, db: Session = Depends(get_db)):
    admin = db.query(User).filter(User.id == admin_id, User.role == RoleEnum.SCHOOL_ADMIN).first()
    if not admin:
        raise HTTPException(status_code=404, detail="School Admin not found.")

    update_data = data.dict(exclude_unset=True)
    if "email" in update_data:
        if db.query(User).filter(User.email == update_data["email"], User.id != admin_id).first():
            raise HTTPException(status_code=400, detail="Email already taken.")

    for key, value in update_data.items():
        setattr(admin, key, value)

    db.commit()
    return {"message": "School Admin updated successfully"}

@router.delete("/school-admins/{admin_id}", dependencies=[verify_super_admin])
def delete_school_admin(admin_id: int, db: Session = Depends(get_db)):
    admin = db.query(User).filter(User.id == admin_id, User.role == RoleEnum.SCHOOL_ADMIN).first()
    if not admin:
        raise HTTPException(status_code=404, detail="School Admin not found.")
    db.delete(admin)
    db.commit()
    return {"message": "School Admin deleted successfully."}


# ==========================================
# 3. GLOBAL CLASS & SECTIONS CRUD (Requirement #1)
# ==========================================

@router.post("/classes-with-sections", status_code=status.HTTP_201_CREATED, dependencies=[verify_super_admin])
def add_class_with_sections(data: ClassWithSectionCreate, db: Session = Depends(get_db)):
    existing_class = db.query(ClassModel).filter(
        ClassModel.class_name == data.class_name
    ).first()

    if existing_class:
        class_obj = existing_class
    else:
        class_obj = ClassModel(
            class_name=data.class_name,
            grade_level=data.grade_level
        )
        db.add(class_obj)
        db.flush()

    added_secs = []
    for sec_name in data.sections:
        if not db.query(ClassSection).filter(ClassSection.class_id == class_obj.id, ClassSection.section_name == sec_name).first():
            db.add(ClassSection(class_id=class_obj.id, section_name=sec_name))
            added_secs.append(sec_name)

    db.commit()
    return {"message": "Global class and sections configured successfully", "class_id": class_obj.id, "added_sections": added_secs}

@router.get("/classes-with-sections", dependencies=[verify_super_admin])
def get_classes_summary(db: Session = Depends(get_db)):
    classes = db.query(ClassModel).all()
    
    result = []
    for c in classes:
        sec_names = [{"section_id": s.id, "section_name": s.section_name} for s in c.sections]
        result.append({
            "class_id": c.id,
            "class_name": c.class_name,
            "grade_level": c.grade_level,
            "total_sections": len(sec_names),
            "sections": sec_names
        })
    return result

@router.put("/classes-with-sections/{class_id}", dependencies=[verify_super_admin])
def edit_class(class_id: int, data: ClassWithSectionUpdate, db: Session = Depends(get_db)):
    class_obj = db.query(ClassModel).filter(ClassModel.id == class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found.")

    if data.class_name:
        class_obj.class_name = data.class_name
    if data.grade_level:
        class_obj.grade_level = data.grade_level
    
    if data.sections is not None:
        existing_sections = {sec.section_name: sec for sec in class_obj.sections}
        new_section_set = set(data.sections)

        for sec_name in new_section_set:
            if sec_name not in existing_sections:
                db.add(ClassSection(class_id=class_obj.id, section_name=sec_name))
        
        for sec_name, sec_obj in existing_sections.items():
            if sec_name not in new_section_set:
                db.delete(sec_obj)

    db.commit()
    return {"message": "Global class and sections updated successfully"}

@router.delete("/classes-with-sections/{class_id}", dependencies=[verify_super_admin])
def delete_class(class_id: int, db: Session = Depends(get_db)):
    class_obj = db.query(ClassModel).filter(ClassModel.id == class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found.")
    db.delete(class_obj)
    db.commit()
    return {"message": "Class deleted successfully."}


# ==========================================
# 4. SUBJECT CRUD & HIERARCHY
# ==========================================

@router.post("/subjects", status_code=status.HTTP_201_CREATED, dependencies=[verify_super_admin])
def add_subject_with_chapters(data: SubjectWithChaptersCreate, db: Session = Depends(get_db)):
    class_obj = db.query(ClassModel).filter(ClassModel.id == data.class_id).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found.")

    if data.section_id:
        section_obj = db.query(ClassSection).filter(ClassSection.id == data.section_id, ClassSection.class_id == data.class_id).first()
        if not section_obj:
            raise HTTPException(status_code=404, detail="Section not found for this class.")

    new_subject = Subject(name=data.name, class_id=data.class_id, section_id=data.section_id)
    db.add(new_subject)
    db.flush()

    for chap in data.chapters:
        new_chapter = Chapter(subject_id=new_subject.id, chapter_name=chap.chapter_name)
        db.add(new_chapter)
        db.flush()

        for top in chap.topics:
            db.add(Topic(chapter_id=new_chapter.id, topic_name=top.topic_name, description=top.description))

    db.commit()
    return {"message": "Subject added successfully", "subject_id": new_subject.id}

@router.get("/subjects", dependencies=[verify_super_admin])
def get_subjects_summary(class_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(Subject)
    if class_id:
        query = query.filter(Subject.class_id == class_id)
    subjects = query.all()

    result = []
    for sub in subjects:
        chapters_list = []
        for chap in sub.chapters:
            topics_list = [{"topic_id": t.id, "topic_name": t.topic_name, "description": t.description} for t in chap.topics]
            chapters_list.append({
                "chapter_id": chap.id,
                "chapter_name": chap.chapter_name,
                "total_topics": len(topics_list),
                "topics": topics_list
            })

        cls = sub.class_obj
        sec_list = [{"section_id": s.id, "section_name": s.section_name} for s in cls.sections] if cls else []

        result.append({
            "subject_id": sub.id,
            "subject_name": sub.name,
            "total_chapters": len(chapters_list),
            "chapters": chapters_list,
            "class_info": {
                "class_id": cls.id if cls else None,
                "class_name": cls.class_name if cls else None,
                "grade_level": cls.grade_level if cls else None,
                "total_sections": len(sec_list),
                "sections": sec_list
            }
        })
    return result

@router.put("/subjects/{subject_id}", dependencies=[verify_super_admin])
def edit_subject(subject_id: int, data: SubjectUpdate, db: Session = Depends(get_db)):
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found.")

    if data.name:
        subject.name = data.name
    if data.class_id:
        if not db.query(ClassModel).filter(ClassModel.id == data.class_id).first():
            raise HTTPException(status_code=404, detail="Class not found.")
        subject.class_id = data.class_id
    if data.section_id is not None:
        subject.section_id = data.section_id

    if data.chapters is not None:
        db.query(Chapter).filter(Chapter.subject_id == subject.id).delete()
        for chap in data.chapters:
            new_chapter = Chapter(subject_id=subject.id, chapter_name=chap.chapter_name)
            db.add(new_chapter)
            db.flush()
            for top in chap.topics:
                db.add(Topic(chapter_id=new_chapter.id, topic_name=top.topic_name, description=top.description))

    db.commit()
    return {"message": "Subject updated successfully"}

@router.delete("/subjects/{subject_id}", dependencies=[verify_super_admin])
def delete_subject(subject_id: int, db: Session = Depends(get_db)):
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found.")
    db.delete(subject)
    db.commit()
    return {"message": "Subject deleted successfully."}


# ==========================================
# 5. TEACHER CRUD & LIST OF CLASSES/SUBJECTS
# ==========================================

@router.post("/teachers", status_code=status.HTTP_201_CREATED, dependencies=[verify_super_admin])
def add_teacher(data: TeacherCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered.")
    if not db.query(School).filter(School.id == data.school_id).first():
        raise HTTPException(status_code=404, detail="School not found.")

    # Fetch classes (global)
    classes = []
    if data.class_ids:
        classes = db.query(ClassModel).filter(ClassModel.id.in_(data.class_ids)).all()
        if len(classes) != len(data.class_ids):
            raise HTTPException(status_code=400, detail="One or more specified classes are invalid.")

    # Fetch subjects
    subjects = []
    if data.subject_ids:
        subjects = db.query(Subject).filter(Subject.id.in_(data.subject_ids)).all()
        if len(subjects) != len(data.subject_ids):
            raise HTTPException(status_code=400, detail="One or more specified subjects are invalid.")

    user = User(
        name=data.name,
        email=data.email,
        password=hash_password(data.password),
        phone_number=data.phone_number,
        gender=data.gender,
        role=RoleEnum.TEACHER
    )
    db.add(user)
    db.flush()

    teacher = Teacher(
        user_id=user.id,
        school_id=data.school_id,
        qualification=data.qualification
    )
    teacher.classes = classes
    teacher.subjects = subjects
    db.add(teacher)
    db.commit()
    return {"message": "Teacher added successfully with assigned classes and subjects", "teacher_id": teacher.id}


@router.put("/teachers/{teacher_id}/assign-classes-subjects", dependencies=[verify_super_admin])
def assign_teacher_classes_and_subjects(teacher_id: int, data: TeacherAssignmentUpdate, db: Session = Depends(get_db)):
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found.")

    classes = db.query(ClassModel).filter(ClassModel.id.in_(data.class_ids)).all()
    if len(classes) != len(data.class_ids):
        raise HTTPException(status_code=400, detail="One or more classes are invalid.")

    subjects = db.query(Subject).filter(Subject.id.in_(data.subject_ids)).all()
    if len(subjects) != len(data.subject_ids):
        raise HTTPException(status_code=400, detail="One or more subjects are invalid.")

    teacher.classes = classes
    teacher.subjects = subjects
    db.commit()
    return {"message": "Teacher class and subject assignments updated successfully", "teacher_id": teacher.id}


@router.get("/teachers", dependencies=[verify_super_admin])
def get_teachers_summary(school_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(Teacher)
    if school_id:
        query = query.filter(Teacher.school_id == school_id)
    teachers = query.all()

    result = []
    for t in teachers:
        user = t.user
        assigned_classes = [{"class_id": c.id, "class_name": c.class_name} for c in t.classes]
        assigned_subjects = [{"subject_id": s.id, "subject_name": s.name} for s in t.subjects]
        
        result.append({
            "teacher_id": t.id,
            "username": user.name if user else "N/A",
            "school_name": t.school.name if t.school else "N/A",
            "email": user.email if user else "N/A",
            "phone": user.phone_number if user else "N/A",
            "qualification": t.qualification,
            "assigned_classes": assigned_classes,
            "assigned_subjects": assigned_subjects,
            "status": user.activation_status.value if user and hasattr(user.activation_status, "value") else "active"
        })
    return result

@router.put("/teachers/{teacher_id}", dependencies=[verify_super_admin])
def edit_teacher(teacher_id: int, data: TeacherUpdate, db: Session = Depends(get_db)):
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found.")

    user = teacher.user
    update_data = data.dict(exclude_unset=True)

    if "email" in update_data:
        if db.query(User).filter(User.email == update_data["email"], User.id != user.id).first():
            raise HTTPException(status_code=400, detail="Email already taken.")
        user.email = update_data.pop("email")

    for key, val in update_data.items():
        if hasattr(user, key):
            setattr(user, key, val)
        elif hasattr(teacher, key):
            setattr(teacher, key, val)

    db.commit()
    return {"message": "Teacher updated successfully"}

@router.delete("/teachers/{teacher_id}", dependencies=[verify_super_admin])
def delete_teacher(teacher_id: int, db: Session = Depends(get_db)):
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found.")
    user = teacher.user
    db.delete(teacher)
    if user:
        db.delete(user)
    db.commit()
    return {"message": "Teacher deleted successfully"}