from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    ForeignKeyConstraint,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from databaseCon import Base


class TeacherQuizPublication(Base):
    __tablename__ = "teacher_quiz_publication"
    __table_args__ = (
        UniqueConstraint(
            "question_set_id",
            "section_id",
            name="uq_teacher_quiz_publication_section",
        ),
        CheckConstraint(
            "published_by > 0",
            name="ck_teacher_quiz_publication_published_by_positive",
        ),
        ForeignKeyConstraint(
            ["question_set_id", "class_id"],
            ["question_set.id", "question_set.class_id"],
            name="fk_teacher_quiz_publication_question_set_class",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["section_id", "class_id"],
            ["class_section.id", "class_section.class_id"],
            name="fk_teacher_quiz_publication_section_class",
            ondelete="CASCADE",
        ),
        Index("ix_teacher_quiz_publication_section", "section_id"),
        Index("ix_teacher_quiz_publication_class", "class_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    question_set_id = Column(
        Integer,
        ForeignKey("question_set.id", ondelete="CASCADE"),
        nullable=False,
    )
    class_id = Column(
        Integer,
        ForeignKey("class.id", ondelete="RESTRICT"),
        nullable=False,
    )
    section_id = Column(
        Integer,
        ForeignKey("class_section.id", ondelete="CASCADE"),
        nullable=False,
    )
    published_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    published_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    question_set = relationship("QuestionSet", foreign_keys=[question_set_id])
    section = relationship("ClassSection", foreign_keys=[section_id])
    publisher = relationship("User")
