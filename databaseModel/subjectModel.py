from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import relationship

from databaseCon import Base
from databaseModel.classModel import class_subjects, teacher_subjects


class Subject(Base):
    __tablename__ = "subject"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)

    classes = relationship("ClassModel", secondary=class_subjects, back_populates="subjects")
    teachers = relationship("Teacher", secondary=teacher_subjects, back_populates="subjects")
    chapters = relationship(
        "Chapter",
        back_populates="subject",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )