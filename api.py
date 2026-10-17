print(">>> RUNNING CORRECT API.PY <<<")

# FastAPI core
from fastapi import FastAPI, Request, Form, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# Database + ORM
from sqlalchemy.orm import Session
from database.database import get_db

# Security
from utils.security import verify_password

# Logging
import logging

# Failed login attempt logging
logging.basicConfig(
    filename="login_attempts.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ---------------------------------------------------------
# Demo student data
# ---------------------------------------------------------
students = [
    {"id": "1001", "name": "John Doe", "grade": "10"},
    {"id": "1002", "name": "Jane Smith", "grade": "11"},
    {"id": "1003", "name": "Michael Johnson", "grade": "12"},
]

# ---------------------------------------------------------
# Demo teacher data
# ---------------------------------------------------------
teachers = [
    {"id": "T001", "name": "Mrs. Anderson", "subject": "Math"},
    {"id": "T002", "name": "Mr. Brown", "subject": "Science"},
    {"id": "T003", "name": "Ms. Carter", "subject": "English"},
]

from business_logic.uma.uma_service import UmaService
from business_logic.siem.student_service import StudentService
from business_logic.amg.scheduling_service import scheduling_service, CapacityLimitError

# ---------------------------------------------------------
# Create FastAPI app FIRST
# ---------------------------------------------------------
app = FastAPI()

# ---------------------------------------------------------
# Mount static folder (CSS, images, JS)
# ---------------------------------------------------------
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------------------------------------------------------
# Templates setup
# ---------------------------------------------------------
templates = Jinja2Templates(directory="templates")
templates.env.cache = None   # Fixes Jinja2 caching bug

# ---------------------------------------------------------
# Business logic service
# ---------------------------------------------------------
uma = UmaService()
student_service = StudentService()

# ---------------------------------------------------------
# LOGIN ROUTES
# ---------------------------------------------------------
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"request": request})


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    stored_user = {
        "username": "admin",
        "hashed_password": "$2b$12$FJN3VZMycl1zSuvBXw9CbeagX9kP3qU6ZLEyxjHMPGpgqu8gnUtZW"
    }

    # Successful login
    if username == stored_user["username"] and verify_password(password, stored_user["hashed_password"]):
        logging.info(f"Successful login for user: {username}")
        return RedirectResponse("/dashboard", status_code=302)

    # Failed login
    logging.warning(f"Failed login attempt for username: {username}")
    return templates.TemplateResponse(
        request,
        "login.html",
        {"request": request, "error": "Invalid username or password"}
    )

# ---------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {"request": request})

# ---------------------------------------------------------
# STUDENTS PAGE
# ---------------------------------------------------------
@app.get("/students", response_class=HTMLResponse)
def students_page(request: Request):
    return templates.TemplateResponse(
        request,
        "students.html",
        {"request": request, "students": student_service.list_students()}
    )

# ---------------------------------------------------------
# COURSE SCHEDULING ENROLLMENT (AMG-007 / T1-024)
# ---------------------------------------------------------
@app.post("/sections/{section_id}/enroll")
def enroll_student(
    section_id: int,
    student_id: int = Query(..., description="ID of the student to enroll"),
    db: Session = Depends(get_db)
):
    try:
        enrollment = scheduling_service.enroll_student(db, section_id, student_id)
        return {"message": "Enrollment successful", "enrollment_id": enrollment.id}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (CapacityLimitError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---------------------------------------------------------
# ADD STUDENT (SIEM-004: T1-016 form, T1-018 validation)
# ---------------------------------------------------------
@app.get("/students/new", response_class=HTMLResponse)
def new_student_form(request: Request):
    return templates.TemplateResponse(
        request,
        "student_form.html",
        {"request": request, "form": {}, "errors": {}}
    )


@app.post("/students/new", response_class=HTMLResponse)
async def create_student(request: Request):
    form = dict(await request.form())
    student_id, errors = student_service.create_student(form)

    # Show the form again with the user's entries and error messages.
    if errors:
        return templates.TemplateResponse(
            request,
            "student_form.html",
            {"request": request, "form": form, "errors": errors},
            status_code=400
        )

    return RedirectResponse(f"/ui/student/{student_id}", status_code=303)

# ---------------------------------------------------------
# TEACHERS PAGE
# ---------------------------------------------------------
@app.get("/teachers", response_class=HTMLResponse)
def teachers_page(request: Request):
    return templates.TemplateResponse(
        request,
        "teachers.html",
        {"request": request, "teachers": teachers}
    )

# ---------------------------------------------------------
# TEACHER PROFILE PAGE
# ---------------------------------------------------------
@app.get("/ui/teacher/{teacher_id}", response_class=HTMLResponse)
def teacher_ui(request: Request, teacher_id: str):
    teacher = next((t for t in teachers if t["id"] == teacher_id), None)
    return templates.TemplateResponse(
        request,
        "teacher_profile.html",
        {"request": request, "teacher": teacher}
    )

# ---------------------------------------------------------
# HOME PAGE
# ---------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "home.html", {"request": request})

# ---------------------------------------------------------
# STUDENT UI PAGE
# ---------------------------------------------------------
@app.get("/ui/student/{student_id}", response_class=HTMLResponse)
def student_ui(request: Request, student_id: str):
    student = student_service.get_student(student_id)
    return templates.TemplateResponse(
        request,
        "student_profile.html",
        {"request": request, "student": student},
        status_code=200 if student else 404
    )