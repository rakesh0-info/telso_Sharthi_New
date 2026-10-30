from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from databaseCon import engine, SessionLocal, Base
import admin_seed
import databaseModel.userModel
import databaseModel.schoolModel
import databaseModel.teacherModel
import databaseModel.studentModel
import databaseModel.classroomOperatorModel
import databaseModel.classModel
# Add these two imports:
import databaseModel.subjectModel
import databaseModel.chapterModel


from controller.publicController import router as public
from controller.SuperAdminController import router as super_admin



Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup Logic ---
    db = SessionLocal()
    try:
        admin_seed.seed_admin_user(db)
    finally:
        db.close()
        
    yield  


app = FastAPI(lifespan=lifespan)

app.include_router(public)
app.include_router(super_admin)