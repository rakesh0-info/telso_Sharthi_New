from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import relationship

from databaseCon import Base


class TeacherLessonContent(Base):
    __tablename__ = "teacher_lesson_content"
    __table_args__ = (
        CheckConstraint(
            "status IN ('in_progress', 'done', 'shared')",
            name="ck_teacher_lesson_content_status",
        ),
        CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_teacher_lesson_content_name_nonempty",
        ),
        CheckConstraint(
            "length(trim(content)) > 0",
            name="ck_teacher_lesson_content_content_nonempty",
        ),
        Index("ix_teacher_lesson_school_class", "school_id", "class_id"),
        Index("ix_teacher_lesson_section", "section_id"),
        Index("ix_teacher_lesson_created_by", "created_by"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(150), nullable=False)
    content = Column(Text, nullable=False)
    content_type = Column(String(30), nullable=False, default="lesson")
    generated_by_ai = Column(Boolean, nullable=False, default=True)
    status = Column(String(20), nullable=False, default="done")
    status_before_share = Column(String(20), nullable=True)

    school_id = Column(
        Integer, ForeignKey("school.id", ondelete="RESTRICT"), nullable=False
    )
    class_id = Column(
        Integer, ForeignKey("class.id", ondelete="RESTRICT"), nullable=False
    )
    section_id = Column(
        Integer, ForeignKey("class_section.id", ondelete="RESTRICT"), nullable=False
    )
    subject_id = Column(
        Integer, ForeignKey("subject.id", ondelete="RESTRICT"), nullable=False
    )
    chapter_id = Column(
        Integer, ForeignKey("chapter.id", ondelete="RESTRICT"), nullable=False
    )
    topic_id = Column(
        Integer, ForeignKey("topic.id", ondelete="RESTRICT"), nullable=True
    )
    created_by = Column(
        Integer, ForeignKey("teacher.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(
        Integer, ForeignKey("teacher.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    school = relationship("School")
    class_obj = relationship("ClassModel")
    section = relationship("ClassSection")
    subject = relationship("Subject")
    chapter = relationship("Chapter")
    topic = relationship("Topic")
    creator = relationship("Teacher", foreign_keys=[created_by])
    deleter = relationship("Teacher", foreign_keys=[deleted_by])
    shares = relationship(
        "TeacherLessonShare",
        back_populates="lesson",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class TeacherLessonShare(Base):
    __tablename__ = "teacher_lesson_share"
    __table_args__ = (
        Index(
            "uq_teacher_lesson_active_section_share",
            "lesson_id",
            "section_id",
            unique=True,
            postgresql_where=text("student_id IS NULL AND revoked_at IS NULL"),
            sqlite_where=text("student_id IS NULL AND revoked_at IS NULL"),
        ),
        Index(
            "uq_teacher_lesson_active_student_share",
            "lesson_id",
            "student_id",
            unique=True,
            postgresql_where=text("student_id IS NOT NULL AND revoked_at IS NULL"),
            sqlite_where=text("student_id IS NOT NULL AND revoked_at IS NULL"),
        ),
        Index("ix_teacher_lesson_share_section", "section_id", "revoked_at"),
        CheckConstraint(
            "student_id IS NULL OR student_id > 0",
            name="ck_teacher_lesson_share_student_id_positive",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    lesson_id = Column(
        Integer,
        ForeignKey("teacher_lesson_content.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id = Column(
        Integer, ForeignKey("class_section.id", ondelete="CASCADE"), nullable=False
    )
    student_id = Column(
        Integer, ForeignKey("student.id", ondelete="CASCADE"), nullable=True
    )
    shared_by = Column(
        Integer, ForeignKey("teacher.id", ondelete="SET NULL"), nullable=True
    )
    shared_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_by = Column(
        Integer, ForeignKey("teacher.id", ondelete="SET NULL"), nullable=True
    )

    lesson = relationship("TeacherLessonContent", back_populates="shares")
    section = relationship("ClassSection")
    student = relationship("Student")
    sharer = relationship("Teacher", foreign_keys=[shared_by])
    revoker = relationship("Teacher", foreign_keys=[revoked_by])
