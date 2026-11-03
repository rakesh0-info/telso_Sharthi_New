from sqlalchemy import Column, ForeignKey, Integer, String, Table, UniqueConstraint
from sqlalchemy.orm import relationship

from databaseCon import Base

teacher_classes = Table(
    "teacher_classes",
    Base.metadata,
    Column("teacher_id", Integer, ForeignKey("teacher.id", ondelete="CASCADE"), primary_key=True),
    Column("class_id", Integer, ForeignKey("class.id", ondelete="CASCADE"), primary_key=True),
)

class_subjects = Table(
    "class_subjects",
    Base.metadata,
    Column("class_id", Integer, ForeignKey("class.id", ondelete="CASCADE"), primary_key=True),
    Column("subject_id", Integer, ForeignKey("subject.id", ondelete="CASCADE"), primary_key=True),
)

teacher_subjects = Table(
    "teacher_subjects",
    Base.metadata,
    Column("teacher_id", Integer, ForeignKey("teacher.id", ondelete="CASCADE"), primary_key=True),
    Column("subject_id", Integer, ForeignKey("subject.id", ondelete="CASCADE"), primary_key=True),
)

teacher_sections = Table(
    "teacher_sections",
    Base.metadata,
    Column("teacher_id", Integer, ForeignKey("teacher.id", ondelete="CASCADE"), primary_key=True),
    Column("section_id", Integer, ForeignKey("class_section.id", ondelete="CASCADE"), primary_key=True),
)

school_classes = Table(
    "school_classes",
    Base.metadata,
    Column("school_id", Integer, ForeignKey("school.id", ondelete="CASCADE"), primary_key=True),
    Column("class_id", Integer, ForeignKey("class.id", ondelete="CASCADE"), primary_key=True),
)


class ClassModel(Base):
    __tablename__ = "class"
    __table_args__ = (UniqueConstraint("class_name", name="uq_class_name"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    class_name = Column(String(100), nullable=False)
    grade_level = Column(String(50), nullable=True)

    sections = relationship(
        "ClassSection",
        back_populates="class_obj",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    students = relationship("Student", back_populates="class_obj")
    teachers = relationship("Teacher", secondary=teacher_classes, back_populates="classes")
    subjects = relationship("Subject", secondary=class_subjects, back_populates="classes")

    # Bi-directional relationship for classroom operators assigned to this class
    operator_assignments = relationship(
        "ClassroomOperatorAssignment",
        back_populates="class_obj",
        cascade="all, delete-orphan",
    )


class ClassSection(Base):
    __tablename__ = "class_section"
    __table_args__ = (
        UniqueConstraint("class_id", "section_name", name="uq_class_section_name"),
        UniqueConstraint("id", "class_id", name="uq_class_section_id_class"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    class_id = Column(Integer, ForeignKey("class.id", ondelete="CASCADE"), nullable=False)
    section_name = Column(String(20), nullable=False)

    class_obj = relationship("ClassModel", back_populates="sections")
    students = relationship("Student", back_populates="section_obj")