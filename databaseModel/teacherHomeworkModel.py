from sqlalchemy import (
    and_,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from databaseCon import Base
from databaseModel.classModel import ClassSection


class TeacherHomework(Base):
    __tablename__ = "teacher_homework"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published')",
            name="ck_teacher_homework_status",
        ),
        CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_teacher_homework_name_nonempty",
        ),
        CheckConstraint("file_size > 0", name="ck_teacher_homework_file_size"),
        UniqueConstraint(
            "id",
            "class_id",
            "section_id",
            "school_id",
            name="uq_teacher_homework_target",
        ),
        ForeignKeyConstraint(
            ["section_id", "class_id"],
            ["class_section.id", "class_section.class_id"],
            name="fk_teacher_homework_section_class",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_teacher_homework_target",
            "school_id",
            "class_id",
            "section_id",
            "status",
            "due_date",
        ),
        Index("ix_teacher_homework_owner", "created_by", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(150), nullable=False)
    class_id = Column(
        Integer, ForeignKey("class.id", ondelete="RESTRICT"), nullable=False
    )
    section_id = Column(Integer, nullable=False)
    school_id = Column(
        Integer, ForeignKey("school.id", ondelete="RESTRICT"), nullable=False
    )
    file_path = Column(String(1024), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)
    due_date = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="draft")
    created_by = Column(
        Integer, ForeignKey("teacher.id", ondelete="SET NULL"), nullable=True
    )
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    school = relationship("School")
    class_obj = relationship("ClassModel", foreign_keys=[class_id])
    section = relationship(
        "ClassSection",
        primaryjoin=lambda: and_(
            TeacherHomework.section_id == ClassSection.id,
            TeacherHomework.class_id == ClassSection.class_id,
        ),
        viewonly=True,
    )
    creator = relationship("Teacher")
    submissions = relationship(
        "TeacherHomeworkSubmission",
        back_populates="homework",
        foreign_keys="TeacherHomeworkSubmission.homework_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class TeacherHomeworkSubmission(Base):
    __tablename__ = "teacher_homework_submission"
    __table_args__ = (
        UniqueConstraint(
            "homework_id",
            "student_id",
            name="uq_teacher_homework_submission_student",
        ),
        CheckConstraint(
            "answer_text IS NOT NULL OR file_path IS NOT NULL",
            name="ck_teacher_homework_submission_has_answer",
        ),
        ForeignKeyConstraint(
            ["homework_id", "class_id", "section_id", "school_id"],
            [
                "teacher_homework.id",
                "teacher_homework.class_id",
                "teacher_homework.section_id",
                "teacher_homework.school_id",
            ],
            name="fk_teacher_homework_submission_target",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["section_id", "class_id"],
            ["class_section.id", "class_section.class_id"],
            name="fk_teacher_homework_submission_section_class",
            ondelete="CASCADE",
        ),
        Index(
            "ix_teacher_homework_submission_student",
            "student_id",
            "submitted_at",
        ),
        CheckConstraint(
            "is_late IN (TRUE, FALSE)",
            name="ck_teacher_homework_submission_is_late",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    homework_id = Column(
        Integer,
        ForeignKey("teacher_homework.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_id = Column(
        Integer, ForeignKey("student.id", ondelete="CASCADE"), nullable=False
    )
    school_id = Column(
        Integer, ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    class_id = Column(
        Integer, ForeignKey("class.id", ondelete="CASCADE"), nullable=False
    )
    section_id = Column(Integer, nullable=False)
    answer_text = Column(Text, nullable=True)
    file_path = Column(String(1024), nullable=True)
    original_filename = Column(String(255), nullable=True)
    file_size = Column(Integer, nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=False)
    is_late = Column(Boolean, nullable=False, default=False)

    homework = relationship(
        "TeacherHomework",
        back_populates="submissions",
        foreign_keys=[homework_id],
    )
    student = relationship("Student")
