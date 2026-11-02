from sqlalchemy import Column, Enum as SQLEnum, ForeignKey, Integer, String, Text, Index, func
from sqlalchemy.orm import relationship

from databaseCon import Base
from enums import ContentTypeEnum


class Content(Base):
    __tablename__ = "content"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content_type = Column(SQLEnum(ContentTypeEnum, name="enm_content_type"), nullable=False)
    title = Column(String(255), nullable=False)
    content_code = Column(String(100), unique=True, index=True, nullable=True)
    description = Column(Text, nullable=True)

    # References based on your architecture
    school_id = Column(Integer, ForeignKey("school.id", ondelete="CASCADE"), nullable=False)
    class_id = Column(Integer, ForeignKey("class.id", ondelete="CASCADE"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subject.id", ondelete="CASCADE"), nullable=False)
    chapter_id = Column(Integer, ForeignKey("chapter.id", ondelete="CASCADE"), nullable=True)
    topic_id = Column(Integer, ForeignKey("topic.id", ondelete="CASCADE"), nullable=True)

    keywords = Column(Text, nullable=True)  # Comma-separated tags

    # File paths or storage references for multi-language support
    english_file_url = Column(String(500), nullable=True)
    manipuri_file_url = Column(String(500), nullable=True)

    uploaded_by= Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    school = relationship("School")
    class_obj = relationship("ClassModel")
    subject = relationship("Subject")
    chapter = relationship("Chapter")
    topic = relationship("Topic")
    uploader = relationship("User", foreign_keys=[uploaded_by])


Index("uq_content_code_lower", func.lower(Content.content_code), unique=True)