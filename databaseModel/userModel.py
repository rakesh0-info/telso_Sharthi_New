from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SQLEnum,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import relationship, synonym

from databaseCon import Base
from enums import ActivationStatus, GenderEnum, RoleEnum
from databaseModel.schoolAdminAssociation import school_admin_assignments


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    phone_number = Column(String(10), nullable=True)

    gender = Column(
        SQLEnum(GenderEnum, name="enm_gender", inherit_schema=True),
        nullable=True,
    )
    role = Column(
        SQLEnum(RoleEnum, name="enm_role", inherit_schema=True),
        nullable=False,
    )
    activation_status = Column(
        SQLEnum(ActivationStatus, name="enm_activation", inherit_schema=True),
        default=ActivationStatus.ACTIVE,
        nullable=False,
    )

    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    otp = Column(String(10), nullable=True)
    otp_expiry = Column(DateTime, nullable=True)

    phonenumber = synonym("phone_number")
    lastlogin = synonym("last_login")

    administered_schools = relationship(
        "School",
        secondary=school_admin_assignments,
        back_populates="school_admins",
        lazy="selectin",
    )

    teacher_profile = relationship(
        "Teacher",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    operator_profile = relationship(
        "ClassroomOperator",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )


Index("uq_users_email_lower", func.lower(User.email), unique=True)