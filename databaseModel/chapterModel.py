from sqlalchemy import Column, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from databaseCon import Base


class Chapter(Base):
    __tablename__ = "chapter"
    __table_args__ = (UniqueConstraint("subject_id", "chapter_name", name="uq_subject_chapter_name"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    subject_id = Column(Integer, ForeignKey("subject.id", ondelete="CASCADE"), nullable=False)
    chapter_name = Column(String(255), nullable=False)

    subject = relationship("Subject", back_populates="chapters")
    topics = relationship(
        "Topic",
        back_populates="chapter",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Topic(Base):
    __tablename__ = "topic"
    __table_args__ = (UniqueConstraint("chapter_id", "topic_name", name="uq_chapter_topic_name"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    chapter_id = Column(Integer, ForeignKey("chapter.id", ondelete="CASCADE"), nullable=False)
    topic_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    chapter = relationship("Chapter", back_populates="topics")