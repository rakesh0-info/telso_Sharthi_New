# schoolModel.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import relationship, synonym
from databaseCon import Base
from enums import ActivationStatus


class School(Base):
    __tablename__ = "school"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    school_code = Column(String(50), nullable=False, unique=True)
    total_student = Column(Integer, default=0, nullable=False)
    total_teacher = Column(Integer, default=0, nullable=False)
    activation = Column(
        SQLEnum(
            ActivationStatus,
            name="enm_status",
            schema="telso_sharthi",
            inherit_schema=True,
            values_callable=lambda x: [e.value for e in x]
        ),
        default=ActivationStatus.ACTIVE,
        nullable=False
    )
    distc = Column(String(100), nullable=True)
    region = Column(String(100), nullable=True)
    
    school_admin_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    school_ph_no = Column(String(10), nullable=True)
    address = Column(String(200), nullable=True)

    # Synonyms
    school_name = synonym("name")
    School_Code = synonym("school_code")
    District = synonym("distc")
    Region = synonym("region")
    admin_id = synonym("school_admin_id")
    phone = synonym("school_ph_no")
    activation_status = synonym("activation")

    # Relationships (Classes removed)
    school_admin = relationship(
        "User",
        foreign_keys=[school_admin_id],
        back_populates="administered_schools"
    )
    teachers = relationship(
        "Teacher",
        back_populates="school",
        cascade="all, delete-orphan"
    )
    students = relationship(
        "Student",
        back_populates="school",
        cascade="all, delete-orphan"
    )
    operators = relationship(
        "ClassroomOperator",
        back_populates="school",
        cascade="all, delete-orphan"
    )