from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from databaseCon import get_db
from databaseModel.classModel import ClassModel, school_classes
from databaseModel.classroomOperatorModel import (
    ClassroomOperator,
    ClassroomOperatorAssignment,
)
from databaseModel.studentModel import Student
from databaseModel.userModel import User
from enums import RoleEnum
from jwts.DB_Security_Config import require_roles


router = APIRouter(prefix="/api/classroom-operator", tags=["Classroom Operator"])
verify_classroom_operator = require_roles(RoleEnum.CLASSROOM_OPERATOR)


@router.get("/my-classes")
def get_my_classes(
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_classroom_operator),
):
    operator = (
        db.query(ClassroomOperator)
        .filter(ClassroomOperator.user_id == current_user.id)
        .first()
    )
    if operator is None:
        raise HTTPException(
            status_code=404,
            detail="Classroom operator profile was not found.",
        )

    assignments = (
        db.query(ClassroomOperatorAssignment)
        .join(ClassModel, ClassroomOperatorAssignment.class_id == ClassModel.id)
        .join(school_classes, school_classes.c.class_id == ClassModel.id)
        .options(
            selectinload(ClassroomOperatorAssignment.class_obj).selectinload(
                ClassModel.subjects
            )
        )
        .filter(
            ClassroomOperatorAssignment.operator_id == operator.id,
            school_classes.c.school_id == operator.school_id,
        )
        .order_by(ClassModel.class_name, ClassModel.id)
        .all()
    )

    class_ids = [assignment.class_id for assignment in assignments]
    student_counts = {}
    if class_ids:
        student_counts = dict(
            db.query(Student.class_id, func.count(Student.id))
            .filter(
                Student.school_id == operator.school_id,
                Student.class_id.in_(class_ids),
            )
            .group_by(Student.class_id)
            .all()
        )

    return {
        "school_id": operator.school_id,
        "classes": [
            {
                "class_id": assignment.class_obj.id,
                "class_name": assignment.class_obj.class_name,
                "grade_level": assignment.class_obj.grade_level,
                "subjects": [
                    {"subject_id": subject.id, "subject_name": subject.name}
                    for subject in sorted(
                        assignment.class_obj.subjects,
                        key=lambda subject: (subject.name, subject.id),
                    )
                ],
                "total_students": student_counts.get(assignment.class_id, 0),
            }
            for assignment in assignments
        ],
    }
