from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from databaseCon import Base
from databaseModel.classModel import teacher_classes, teacher_sections, teacher_subjects


class Teacher(Base):
    __tablename__ = "teacher"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    school_id = Column(Integer, ForeignKey("school.id", ondelete="CASCADE"), nullable=False)
    qualification = Column(String(255), nullable=True)

    class_id = Column(Integer, ForeignKey("class.id", ondelete="SET NULL"), nullable=True)
    section_id = Column(Integer, ForeignKey("class_section.id", ondelete="SET NULL"), nullable=True)

    user = relationship("User", back_populates="teacher_profile")
    school = relationship("School", back_populates="teachers")
    classes = relationship("ClassModel", secondary=teacher_classes, back_populates="teachers")
    subjects = relationship("Subject", secondary=teacher_subjects, back_populates="teachers")
    sections = relationship("ClassSection", secondary=teacher_sections)