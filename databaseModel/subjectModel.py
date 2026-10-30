# databaseModel/subjectModel.py
from sqlalchemy import Column, Integer, String, ForeignKey, Table
from sqlalchemy.orm import relationship
from databaseCon import Base

# Association table for Teacher <-> Subject (Many-to-Many)
teacher_subjects = Table(
    "teacher_subjects",
    Base.metadata,
    Column("teacher_id", Integer, ForeignKey("teacher.id", ondelete="CASCADE"), primary_key=True),
    Column("subject_id", Integer, ForeignKey("subject.id", ondelete="CASCADE"), primary_key=True)
)

class Subject(Base):
    __tablename__ = "subject"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    class_id = Column(Integer, ForeignKey("class.id", ondelete="CASCADE"), nullable=False)
    section_id = Column(Integer, ForeignKey("class_section.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    class_obj = relationship("ClassModel", back_populates="subjects")
    section_obj = relationship("ClassSection", back_populates="subjects")
    chapters = relationship("Chapter", back_populates="subject", cascade="all, delete-orphan")
    teachers = relationship("Teacher", secondary=teacher_subjects, back_populates="subjects")