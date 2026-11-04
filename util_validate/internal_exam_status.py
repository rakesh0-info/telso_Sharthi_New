from datetime import datetime, timezone

from databaseModel.internalExamModel import InternalExam


def refresh_internal_exam_status(
    exam: InternalExam,
    now: datetime | None = None,
) -> bool:
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    else:
        current_time = current_time.astimezone(timezone.utc)

    start_at = exam.start_at
    if start_at.tzinfo is None or start_at.utcoffset() is None:
        start_at = start_at.replace(tzinfo=timezone.utc)
    else:
        start_at = start_at.astimezone(timezone.utc)

    end_at = exam.end_at
    if end_at.tzinfo is None or end_at.utcoffset() is None:
        end_at = end_at.replace(tzinfo=timezone.utc)
    else:
        end_at = end_at.astimezone(timezone.utc)

    next_status = exam.status
    if exam.status == "scheduled":
        if current_time >= end_at:
            next_status = "completed"
        elif current_time >= start_at:
            next_status = "active"
    elif exam.status == "active" and current_time >= end_at:
        next_status = "completed"

    if next_status == exam.status:
        return False
    exam.status = next_status
    return True
