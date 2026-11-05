import os

from celery import Celery
from dotenv import load_dotenv
from redis import Redis


load_dotenv()




broker_url = (
    os.getenv("CELERY_BROKER_URL")
    
)

celery_app = Celery(
    "telso_sar",
    broker=broker_url,
    include=["tasks"],
)

celery_app.conf.update(
    enable_utc=True,
    timezone="UTC",
    worker_pool="solo" if os.name == "nt" else "prefork",
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "update-internal-exam-statuses-every-30-seconds": {
            "task": "tasks.update_exam_statuses",
            "schedule": 30.0,
        },
    },
)
