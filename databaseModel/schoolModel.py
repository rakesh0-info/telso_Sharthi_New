from sqlalchemy import Column, Enum as SQLEnum, Integer, String
from sqlalchemy.orm import relationship, synonym

from databaseCon import Base
from enums import ActivationStatus
from databaseModel.schoolAdminAssociation import school_admin_assignments


class School(Base):
    __tablename__ = "school"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    school_code = Column(String(50), nullable=False, unique=True, index=True)
    total_student = Column(Integer, default=0, nullable=False)
    total_teacher = Column(Integer, default=0, nullable=False)

    activation = Column(
        SQLEnum(
            ActivationStatus,
            name="enm_status",
            schema=Base.metadata.schema,
            inherit_schema=True,
            values_callable=lambda enum_values: [item.value for item in enum_values],
        ),
        default=ActivationStatus.ACTIVE,
        nullable=False,
    )

    state = Column(String(100), nullable=True)
    distc = Column(String(100), nullable=True)
    region = Column(String(100), nullable=True)
    school_ph_no = Column(String(10), nullable=True)
    address = Column(String(200), nullable=True)

    school_name = synonym("name")
    School_Code = synonym("school_code")
    District = synonym("distc")
    district = synonym("distc")
    Region = synonym("region")
    phone = synonym("school_ph_no")
    activation_status = synonym("activation")

    school_admins = relationship(
        "User",
        secondary=school_admin_assignments,
        back_populates="administered_schools",
        lazy="selectin",
    )

    teachers = relationship(
        "Teacher",
        back_populates="school",
        cascade="all, delete-orphan",
    )
    students = relationship(
        "Student",
        back_populates="school",
        cascade="all, delete-orphan",
    )
    operators = relationship(
        "ClassroomOperator",
        back_populates="school",
        cascade="all, delete-orphan",
    )