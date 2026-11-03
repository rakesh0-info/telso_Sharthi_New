from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    TypeDecorator,
)
from sqlalchemy.orm import relationship

from databaseCon import Base


class _StringListType(TypeDecorator):
    impl = String(50)
    cache_ok = True
    code_map: dict[str, str] = {}

    def process_bind_param(self, value, dialect):
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError("This question-set field must be a list of strings.")
        reverse_codes = {value: key for key, value in self.code_map.items() if len(key) <= 3}
        try:
            encoded = [reverse_codes[item] for item in value]
        except KeyError as exc:
            raise ValueError("This question-set field contains an unsupported value.") from exc
        return ",".join(encoded)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        values = value.split(",")
        return [self.code_map.get(item, item) for item in values]


class QuestionSetTypesType(_StringListType):
    code_map = {
        "m": "mcq",
        "tf": "true_false",
        "sa": "short_answer",
        "la": "long_answer",
        "mtf": "match_the_following",
        "fib": "fill_in_the_blanks",
        "multiple_choice": "mcq",
    }


class QuestionSetLevelsType(_StringListType):
    code_map = {"e": "easy", "m": "medium", "h": "hard"}


class Question(Base):
    __tablename__ = "question"
    __table_args__ = (
        CheckConstraint(
            "length(trim(question_text)) > 0",
            name="ck_question_text_nonempty",
        ),
        CheckConstraint(
            "length(trim(correct_answer)) > 0",
            name="ck_question_answer_nonempty",
        ),
        Index("ix_question_chapter_topic", "chapter_id", "topic_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    question_text = Column(Text, nullable=False)
    options = Column(JSON, nullable=True)
    correct_answer = Column(Text, nullable=False)
    question_type = Column(String(50), nullable=False)
    question_level = Column(String(50), nullable=False)
    language = Column(String(35), nullable=False)
    chapter_id = Column(Integer, ForeignKey("chapter.id", ondelete="RESTRICT"), nullable=False)
    topic_id = Column(Integer, ForeignKey("topic.id", ondelete="RESTRICT"), nullable=True)

    chapter = relationship("Chapter")
    topic = relationship("Topic")


class QuestionSet(Base):
    __tablename__ = "question_set"
    __table_args__ = (
        CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_question_set_name_nonempty",
        ),
        CheckConstraint(
            "question_count BETWEEN 1 AND 500",
            name="ck_question_set_question_count",
        ),
        CheckConstraint(
            "duration_minutes BETWEEN 1 AND 1440",
            name="ck_question_set_duration",
        ),
        Index("ix_question_set_created_by", "created_by"),
        Index("ix_question_set_school_id", "school_id"),
        Index("ix_question_set_section_id", "section_id"),
        Index("ix_question_set_scheduled_at", "scheduled_at"),
        UniqueConstraint("id", "class_id", name="uq_question_set_id_class"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(150), nullable=False)
    school_id = Column(Integer, ForeignKey("school.id", ondelete="RESTRICT"), nullable=False)
    class_id = Column(Integer, ForeignKey("class.id", ondelete="RESTRICT"), nullable=False)
    section_id = Column(
        Integer,
        ForeignKey("class_section.id", ondelete="RESTRICT"),
        nullable=True,
    )
    subject_id = Column(Integer, ForeignKey("subject.id", ondelete="RESTRICT"), nullable=False)
    chapter_id = Column(Integer, ForeignKey("chapter.id", ondelete="RESTRICT"), nullable=False)
    topic_id = Column(Integer, ForeignKey("topic.id", ondelete="RESTRICT"), nullable=True)
    language = Column(String(35), nullable=False)
    question_count = Column(Integer, nullable=False)
    question_type = Column(QuestionSetTypesType(), nullable=False)
    question_level = Column(QuestionSetLevelsType(), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    duration_minutes = Column(Integer, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    school = relationship("School")
    class_obj = relationship("ClassModel")
    section = relationship("ClassSection")
    subject = relationship("Subject")
    chapter = relationship("Chapter")
    topic = relationship("Topic")
    creator = relationship("User")
    items = relationship(
        "QuestionSetItem",
        back_populates="question_set",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QuestionSetItem.position",
    )


class QuestionSetItem(Base):
    __tablename__ = "question_set_item"
    __table_args__ = (
        UniqueConstraint(
            "question_set_id",
            "question_id",
            name="uq_question_set_question",
        ),
        UniqueConstraint(
            "question_set_id",
            "position",
            name="uq_question_set_position",
        ),
        CheckConstraint("position >= 1", name="ck_question_set_item_position"),
        CheckConstraint(
            "length(trim(answer)) > 0",
            name="ck_question_set_item_answer_nonempty",
        ),
        Index("ix_question_set_item_question_id", "question_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    question_set_id = Column(
        Integer,
        ForeignKey("question_set.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id = Column(Integer, ForeignKey("question.id", ondelete="RESTRICT"), nullable=False)
    answer = Column(Text, nullable=False)
    position = Column(Integer, nullable=False)

    question_set = relationship("QuestionSet", back_populates="items")
    question = relationship("Question")
