# databaseModel/chapterModel.py
from sqlalchemy import Column, Integer, String, ForeignKey, Text
from sqlalchemy.orm import relationship
from databaseCon import Base

class Chapter(Base):
    __tablename__ = "chapter"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subject_id = Column(Integer, ForeignKey("subject.id", ondelete="CASCADE"), nullable=False)
    chapter_name = Column(String(255), nullable=False)

    # Relationships
    subject = relationship("Subject", back_populates="chapters")
    topics = relationship("Topic", back_populates="chapter", cascade="all, delete-orphan")


class Topic(Base):
    __tablename__ = "topic"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chapter_id = Column(Integer, ForeignKey("chapter.id", ondelete="CASCADE"), nullable=False)
    topic_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Relationships
    chapter = relationship("Chapter", back_populates="topics")