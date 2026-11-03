from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

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
import databaseModel.schoolAdminAssociation
import databaseModel.questionSetModel
import databaseModel.teacherLessonModel
import databaseModel.teacherQuizModel


from controller.publicController import limiter, router as public
from controller.SuperAdminController import router as super_admin
from controller.SchoolAdminController import router as school_admin
from controller.StudentController import router as student
from controller.commonController import router as common
from controller.TeacherAdminController import router as teacher_admin
from controller.TeacherAdminController import teacher_router as teacher_management



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
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(public)
app.include_router(super_admin)
app.include_router(school_admin)
app.include_router(student)
app.include_router(common)
app.include_router(teacher_admin)
app.include_router(teacher_management)