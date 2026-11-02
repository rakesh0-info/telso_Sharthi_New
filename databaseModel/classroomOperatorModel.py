from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship
from databaseCon import Base

class ClassroomOperator(Base):
    __tablename__ = "classroom_operator"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    school_id = Column(Integer, ForeignKey("school.id", ondelete="CASCADE"), nullable=False)

    user = relationship("User", back_populates="operator_profile")
    school = relationship("School", back_populates="operators")

    class_assignments = relationship(
        "ClassroomOperatorAssignment",
        back_populates="operator",
        cascade="all, delete-orphan"
    )

class ClassroomOperatorAssignment(Base):
    __tablename__ = "classroom_operator_assignment"
    __table_args__ = (
        UniqueConstraint("operator_id", "class_id", name="uq_operator_class_assignment"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    operator_id = Column(Integer, ForeignKey("classroom_operator.id", ondelete="CASCADE"), nullable=False)
    class_id = Column(Integer, ForeignKey("class.id", ondelete="CASCADE"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow)

    operator = relationship("ClassroomOperator", back_populates="class_assignments")
    class_obj = relationship("ClassModel", back_populates="operator_assignments")