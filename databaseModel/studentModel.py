# studentModel.py
from sqlalchemy import Column, Integer, String, Date, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from databaseCon import Base
from enums import GenderEnum

class Student(Base):
    __tablename__ = "student"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    gender = Column(SQLEnum(GenderEnum, name="enm_gender"), nullable=True)
    dob = Column(Date, nullable=True)
    phone_number = Column(String(10), nullable=True)  # 10 digits
    
    school_id = Column(Integer, ForeignKey("school.id", ondelete="CASCADE"), nullable=False)
    class_id = Column(Integer, ForeignKey("class.id", ondelete="SET NULL"), nullable=True)
    section_id = Column(Integer, ForeignKey("class_section.id", ondelete="SET NULL"), nullable=True)

    
    parents_name = Column(String(255), nullable=True)
    parents_ph_no = Column(String(10), nullable=True)  # 10 digits
    parents_email = Column(String(255), unique=True, nullable=True)

   
    school = relationship("School", back_populates="students")
    class_obj = relationship("ClassModel", back_populates="students")
    section_obj = relationship("ClassSection", back_populates="students")