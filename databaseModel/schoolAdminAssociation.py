from sqlalchemy import Column, ForeignKey, Integer, Table

from databaseCon import Base

school_admin_assignments = Table(
    "school_admin_assignments",
    Base.metadata,
    Column(
        "school_id",
        Integer,
        ForeignKey("school.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "admin_id",
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)