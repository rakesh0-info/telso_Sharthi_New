# enums.py
import enum

class RoleEnum(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    SCHOOL_ADMIN = "school_admin"
    TEACHER = "teacher"
    STUDENT = "student"
    CLASSROOM_OPERATOR = "classroom_operator"
    CONTENT_ADMIN = "content_admin"

class ActivationStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"

class GenderEnum(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"

class ContentTypeEnum(enum.Enum):
    TEXT = "Text"
    DOCUMENT = "Document"
    PDF = "PDF"
    WORKSHEET="Worksheet"
    TEXTBOOK="Textbook"