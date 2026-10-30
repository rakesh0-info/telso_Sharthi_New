# userModel.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import relationship, synonym
from databaseCon import Base
from enums import RoleEnum, ActivationStatus, GenderEnum

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    phone_number = Column(String(10), nullable=True)
    gender = Column(SQLEnum(GenderEnum, name="enm_gender"), nullable=True)
    role = Column(SQLEnum(RoleEnum, name="enm_role"), nullable=False)
    activation_status = Column(
        SQLEnum(ActivationStatus, name="enm_activation"),
        default=ActivationStatus.ACTIVE,
        nullable=False
    )
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    otp = Column(String(10), nullable=True)
    otp_expiry = Column(DateTime, nullable=True)

    # Synonyms for backward compatibility
    phonenumber = synonym("phone_number")
    lastlogin = synonym("last_login")

    # Relationships (Cleaned up: removed manual string foreign_keys to prevent NameError)
    administered_schools = relationship(
        "School",
        back_populates="school_admin"
    )
    teacher_profile = relationship(
        "Teacher",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )
    operator_profile = relationship(
        "ClassroomOperator",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )