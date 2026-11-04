import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError

from celery_app import celery_app
from databaseCon import SessionLocal
from databaseModel.internalExamModel import InternalExam


logger = logging.getLogger(__name__)


@celery_app.task(
    name="tasks.update_exam_statuses",
    autoretry_for=(SQLAlchemyError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
    ignore_result=True,
)
def update_exam_statuses() -> dict[str, Any]:
    """Advance exam lifecycle statuses using the database's partial indexes."""
    now = datetime.now(timezone.utc)
    try:
        with SessionLocal.begin() as db:
            activated = db.execute(
                update(InternalExam)
                .where(
                    InternalExam.status == "scheduled",
                    InternalExam.start_at <= now,
                )
                .values(status="active")
                .execution_options(synchronize_session=False)
            )
            completed = db.execute(
                update(InternalExam)
                .where(
                    InternalExam.status == "active",
                    InternalExam.end_at <= now,
                )
                .values(status="completed")
                .execution_options(synchronize_session=False)
            )
            activated_count = max(activated.rowcount or 0, 0)
            completed_count = max(completed.rowcount or 0, 0)
    except SQLAlchemyError:
        logger.exception("Failed to update internal exam statuses.")
        raise

    logger.info(
        "Updated internal exam statuses: activated=%d, completed=%d.",
        activated_count,
        completed_count,
    )
    return {
        "activated": activated_count,
        "completed": completed_count,
        "checked_at": now.isoformat(),
    }
