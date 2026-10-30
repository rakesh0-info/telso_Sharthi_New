
from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from databaseCon import Base

class ClassroomOperator(Base):
    __tablename__ = "classroom_operator"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    school_id = Column(Integer, ForeignKey("school.id", ondelete="CASCADE"), nullable=False)

    # Relationships
    user = relationship("User", back_populates="operator_profile")
    school = relationship("School", back_populates="operators")