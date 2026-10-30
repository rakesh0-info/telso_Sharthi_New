# databaseModel/classModel.py
from sqlalchemy import Column, Integer, String, ForeignKey, Table
from sqlalchemy.orm import relationship
from databaseCon import Base

# Association table for Teacher <-> Class (Many-to-Many)
teacher_classes = Table(
    "teacher_classes",
    Base.metadata,
    Column("teacher_id", Integer, ForeignKey("teacher.id", ondelete="CASCADE"), primary_key=True),
    Column("class_id", Integer, ForeignKey("class.id", ondelete="CASCADE"), primary_key=True)
)

class ClassModel(Base):
    __tablename__ = "class"

    id = Column(Integer, primary_key=True, autoincrement=True)
    class_name = Column(String(100), nullable=False)
    grade_level = Column(String(50), nullable=True)

    # Relationships (Global: no school relationship)
    sections = relationship("ClassSection", back_populates="class_obj", cascade="all, delete-orphan")
    students = relationship("Student", back_populates="class_obj", cascade="all, delete-orphan")
    teachers = relationship("Teacher", secondary=teacher_classes, back_populates="classes")
    subjects = relationship("Subject", back_populates="class_obj", cascade="all, delete-orphan")


class ClassSection(Base):
    __tablename__ = "class_section"

    id = Column(Integer, primary_key=True, autoincrement=True)
    class_id = Column(Integer, ForeignKey("class.id", ondelete="CASCADE"), nullable=False)
    section_name = Column(String(20), nullable=False)  # e.g., 'A', 'B', 'C'

    # Relationships
    class_obj = relationship("ClassModel", back_populates="sections")
    students = relationship("Student", back_populates="section_obj", cascade="all, delete-orphan")
    subjects = relationship("Subject", back_populates="section_obj", cascade="all, delete-orphan")