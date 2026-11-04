import enum
from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    and_,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import relationship

from databaseCon import Base
from databaseModel.classModel import ClassSection
from databaseModel.questionSetModel import QuestionSetLevelsType, QuestionSetTypesType


class InternalExamType(str, enum.Enum):
    INTERNAL = "internal"
    SURPRISE_TEST = "surprise_test"


class InternalExam(Base):
    __tablename__ = "internal_exam"
    __table_args__ = (
        CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_internal_exam_name_nonempty",
        ),
        CheckConstraint(
            "question_count BETWEEN 1 AND 50",
            name="ck_internal_exam_question_count",
        ),
        CheckConstraint(
            "duration_minutes BETWEEN 1 AND 1440",
            name="ck_internal_exam_duration",
        ),
        CheckConstraint(
            "status IN ('scheduled', 'active', 'completed', 'cancelled')",
            name="ck_internal_exam_status",
        ),
        UniqueConstraint(
            "id",
            "class_id",
            "section_id",
            "school_id",
            name="uq_internal_exam_target",
        ),
        ForeignKeyConstraint(
            ["section_id", "class_id"],
            ["class_section.id", "class_section.class_id"],
            name="fk_internal_exam_section_class",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_internal_exam_target",
            "school_id",
            "class_id",
            "section_id",
            "start_at",
        ),
        Index(
            "ix_internal_exam_pending_section_start",
            "school_id",
            "class_id",
            "section_id",
            "start_at",
            postgresql_where=text("status = 'scheduled'"),
        ),
        Index(
            "ix_internal_exam_active_section_end",
            "school_id",
            "class_id",
            "section_id",
            "end_at",
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_internal_exam_creator", "created_by", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(150), nullable=False)
    exam_type = Column(
        SQLEnum(
            InternalExamType,
            name="internal_exam_type",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        nullable=False,
    )
    school_id = Column(Integer, ForeignKey("school.id", ondelete="RESTRICT"), nullable=False)
    class_id = Column(Integer, ForeignKey("class.id", ondelete="RESTRICT"), nullable=False)
    section_id = Column(Integer, nullable=False)
    subject_id = Column(Integer, ForeignKey("subject.id", ondelete="RESTRICT"), nullable=False)
    chapter_id = Column(Integer, ForeignKey("chapter.id", ondelete="RESTRICT"), nullable=False)
    topic_id = Column(Integer, ForeignKey("topic.id", ondelete="RESTRICT"), nullable=True)
    language = Column(String(35), nullable=False)
    question_count = Column(Integer, nullable=False)
    question_type = Column(QuestionSetTypesType(), nullable=False)
    question_level = Column(QuestionSetLevelsType(), nullable=False)
    start_at = Column(DateTime(timezone=True), nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(20), nullable=False, default="scheduled")
    created_by = Column(Integer, ForeignKey("teacher.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    school = relationship("School")
    class_obj = relationship("ClassModel")
    section = relationship(
        "ClassSection",
        primaryjoin=lambda: and_(
            InternalExam.section_id == ClassSection.id,
            InternalExam.class_id == ClassSection.class_id,
        ),
        viewonly=True,
    )
    subject = relationship("Subject")
    chapter = relationship("Chapter")
    topic = relationship("Topic")
    creator = relationship("Teacher")
    items = relationship(
        "InternalExamItem",
        back_populates="exam",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="InternalExamItem.position",
    )
    attempts = relationship(
        "InternalExamAttempt",
        back_populates="exam",
        foreign_keys=lambda: [InternalExamAttempt.exam_id],
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    results = relationship(
        "InternalExamResult",
        back_populates="exam",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class InternalExamItem(Base):
    __tablename__ = "internal_exam_question"
    __table_args__ = (
        UniqueConstraint(
            "exam_id",
            "position",
            name="uq_internal_exam_question_exam_position",
        ),
        CheckConstraint("position >= 1", name="ck_internal_exam_item_position"),
        CheckConstraint(
            "length(trim(question_text)) > 0",
            name="ck_internal_exam_question_text_nonempty",
        ),
        CheckConstraint(
            "length(trim(answer)) > 0",
            name="ck_internal_exam_item_answer_nonempty",
        ),
        Index("ix_internal_exam_question_exam_id", "exam_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    exam_id = Column(
        Integer,
        ForeignKey("internal_exam.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_text = Column(Text, nullable=False)
    options = Column(JSON, nullable=True)
    answer = Column(Text, nullable=False)
    question_type = Column(String(50), nullable=False)
    question_level = Column(String(50), nullable=False)
    position = Column(Integer, nullable=False)

    exam = relationship("InternalExam", back_populates="items")


class InternalExamAttempt(Base):
    __tablename__ = "internal_exam_attempt"
    __table_args__ = (
        UniqueConstraint(
            "exam_id",
            "student_id",
            name="uq_internal_exam_attempt_student",
        ),
        CheckConstraint(
            "has_joined IN (TRUE, FALSE)",
            name="ck_internal_exam_attempt_has_joined",
        ),
        ForeignKeyConstraint(
            ["exam_id", "class_id", "section_id", "school_id"],
            [
                "internal_exam.id",
                "internal_exam.class_id",
                "internal_exam.section_id",
                "internal_exam.school_id",
            ],
            name="fk_internal_exam_attempt_target",
            ondelete="CASCADE",
        ),
        Index("ix_internal_exam_attempt_student", "student_id", "joined_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    exam_id = Column(
        Integer,
        ForeignKey("internal_exam.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_id = Column(Integer, ForeignKey("student.id", ondelete="CASCADE"), nullable=False)
    school_id = Column(Integer, ForeignKey("school.id", ondelete="CASCADE"), nullable=False)
    class_id = Column(Integer, ForeignKey("class.id", ondelete="CASCADE"), nullable=False)
    section_id = Column(Integer, nullable=False)
    has_joined = Column(Boolean, nullable=False, default=True)
    joined_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    exam = relationship(
        "InternalExam",
        back_populates="attempts",
        foreign_keys=[exam_id],
    )
    student = relationship("Student")


class InternalExamResult(Base):
    __tablename__ = "internal_exam_result"
    __table_args__ = (
        UniqueConstraint(
            "exam_id",
            "student_id",
            name="uq_internal_exam_result_exam_student",
        ),
        UniqueConstraint(
            "id",
            "exam_id",
            name="uq_internal_exam_result_id_exam",
        ),
        ForeignKeyConstraint(
            ["exam_id", "student_id"],
            [
                "internal_exam_attempt.exam_id",
                "internal_exam_attempt.student_id",
            ],
            name="fk_internal_exam_result_attempt",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "total_marks >= 0 AND max_marks >= total_marks",
            name="ck_internal_exam_result_marks",
        ),
        CheckConstraint(
            "max_marks BETWEEN 1 AND 150",
            name="ck_internal_exam_result_max_marks",
        ),
        CheckConstraint(
            "grading_status IN ('pending_manual', 'graded')",
            name="ck_internal_exam_result_grading_status",
        ),
        Index("ix_internal_exam_result_student", "student_id", "submitted_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    exam_id = Column(
        Integer,
        ForeignKey("internal_exam.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_id = Column(Integer, ForeignKey("student.id", ondelete="CASCADE"), nullable=False)
    total_marks = Column(Integer, nullable=False, default=0)
    max_marks = Column(Integer, nullable=False)
    grading_status = Column(String(20), nullable=False, default="graded")
    submitted_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    exam = relationship("InternalExam", back_populates="results")
    student = relationship("Student")
    responses = relationship(
        "StudentExamResponse",
        back_populates="result",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="StudentExamResponse.question_id",
    )


class StudentExamResponse(Base):
    __tablename__ = "student_exam_response"
    __table_args__ = (
        UniqueConstraint(
            "result_id",
            "question_id",
            name="uq_student_exam_response_result_question",
        ),
        ForeignKeyConstraint(
            ["result_id", "exam_id"],
            ["internal_exam_result.id", "internal_exam_result.exam_id"],
            name="fk_student_exam_response_result_exam",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "marks_awarded IS NULL OR marks_awarded BETWEEN 0 AND 3",
            name="ck_student_exam_response_marks",
        ),
        CheckConstraint(
            "grading_status IN ('pending', 'graded')",
            name="ck_student_exam_response_grading_status",
        ),
        CheckConstraint(
            "(grading_status = 'pending' AND marks_awarded IS NULL AND is_correct IS NULL) "
            "OR (grading_status = 'graded' AND marks_awarded IS NOT NULL AND is_correct IS NOT NULL)",
            name="ck_student_exam_response_grade_consistency",
        ),
        Index("ix_student_exam_response_exam_question", "exam_id", "question_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    result_id = Column(Integer, nullable=False)
    exam_id = Column(Integer, nullable=False)
    question_id = Column(
        Integer,
        ForeignKey("internal_exam_question.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_answer = Column(Text, nullable=False)
    marks_awarded = Column(Integer, nullable=True)
    is_correct = Column(Boolean, nullable=True)
    grading_status = Column(String(20), nullable=False)
    graded_by = Column(Integer, ForeignKey("teacher.id", ondelete="SET NULL"), nullable=True)
    graded_at = Column(DateTime(timezone=True), nullable=True)

    result = relationship("InternalExamResult", back_populates="responses")
    question = relationship("InternalExamItem")
    grader = relationship("Teacher")


def _set_exam_end_at(_mapper, _connection, exam: InternalExam) -> None:
    _ = (_mapper, _connection)
    if exam.start_at is None or exam.duration_minutes is None:
        return
    start_at = exam.start_at
    if start_at.tzinfo is None or start_at.utcoffset() is None:
        start_at = start_at.replace(tzinfo=timezone.utc)
    exam.end_at = start_at + timedelta(minutes=exam.duration_minutes)


event.listen(InternalExam, "before_insert", _set_exam_end_at)
event.listen(InternalExam, "before_update", _set_exam_end_at)
