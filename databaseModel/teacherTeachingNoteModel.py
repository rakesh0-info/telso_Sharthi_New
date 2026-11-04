from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import relationship

from databaseCon import Base


class TeacherTeachingNote(Base):
    __tablename__ = "teacher_teaching_note"
    __table_args__ = (
        CheckConstraint(
            "status IN ('created', 'shared')",
            name="ck_teacher_teaching_note_status",
        ),
        CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_teacher_teaching_note_name_nonempty",
        ),
        CheckConstraint(
            "length(trim(content)) > 0",
            name="ck_teacher_teaching_note_content_nonempty",
        ),
        ForeignKeyConstraint(
            ["section_id", "class_id"],
            ["class_section.id", "class_section.class_id"],
            name="fk_teacher_teaching_note_section_class",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_teacher_teaching_note_owner",
            "created_by",
            "deleted_at",
        ),
        Index(
            "ix_teacher_teaching_note_school_class",
            "school_id",
            "class_id",
            "section_id",
            "subject_id",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(150), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="created")
    school_id = Column(
        Integer, ForeignKey("school.id", ondelete="RESTRICT"), nullable=False
    )
    class_id = Column(
        Integer, ForeignKey("class.id", ondelete="RESTRICT"), nullable=False
    )
    section_id = Column(Integer, nullable=False)
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
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    school = relationship("School")
    class_obj = relationship("ClassModel")
    section = relationship("ClassSection", overlaps="class_obj")
    subject = relationship("Subject")
    chapter = relationship("Chapter")
    topic = relationship("Topic")
    creator = relationship("Teacher")
    shares = relationship(
        "TeacherTeachingNoteShare",
        back_populates="note",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class TeacherTeachingNoteShare(Base):
    __tablename__ = "teacher_teaching_note_share"
    __table_args__ = (
        Index(
            "uq_teacher_teaching_note_active_section",
            "note_id",
            "section_id",
            unique=True,
            postgresql_where=text("student_id IS NULL"),
            sqlite_where=text("student_id IS NULL"),
        ),
        Index(
            "uq_teacher_teaching_note_active_student",
            "note_id",
            "student_id",
            unique=True,
            postgresql_where=text("student_id IS NOT NULL"),
            sqlite_where=text("student_id IS NOT NULL"),
        ),
        ForeignKeyConstraint(
            ["section_id", "class_id"],
            ["class_section.id", "class_section.class_id"],
            name="fk_teacher_teaching_note_share_section_class",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "student_id IS NULL OR student_id > 0",
            name="ck_teacher_teaching_note_share_student_id_positive",
        ),
        Index("ix_teacher_teaching_note_share_section", "section_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    note_id = Column(
        Integer,
        ForeignKey("teacher_teaching_note.id", ondelete="CASCADE"),
        nullable=False,
    )
    class_id = Column(
        Integer, ForeignKey("class.id", ondelete="CASCADE"), nullable=False
    )
    section_id = Column(Integer, nullable=False)
    student_id = Column(
        Integer, ForeignKey("student.id", ondelete="CASCADE"), nullable=True
    )
    shared_by = Column(
        Integer, ForeignKey("teacher.id", ondelete="SET NULL"), nullable=True
    )
    shared_at = Column(DateTime(timezone=True), nullable=False)

    note = relationship("TeacherTeachingNote", back_populates="shares")
    section = relationship("ClassSection")
    student = relationship("Student")
    sharer = relationship("Teacher")
