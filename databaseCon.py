
import os
from dotenv import load_dotenv
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is not set."
    )

SCHEMA_NAME = "telso_sar"


engine_options = {
    "pool_pre_ping": True
}

engine = create_engine(
    DATABASE_URL,
    **engine_options
)



SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

try:

    with engine.connect() as connection:

        connection.execute(
            text("SELECT 1")
        )

    print(
        "Database connection successful."
    )
except Exception as e:
    original_error = getattr(e, "orig", e)
    
    error_message = str(original_error).splitlines()[0]

    print ("error _message")


metadata = MetaData(schema=SCHEMA_NAME)

Base = declarative_base(metadata=metadata)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

