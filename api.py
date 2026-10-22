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
from starlette.middleware.sessions import SessionMiddleware

from utils.security import verify_password
from auth.session import (
    SESSION_MAX_AGE,
    authenticate,
    current_actor,
    login_user,
    logout_user,
    session_secret,
)
from data_access.repositories.student_repository import (
    AccessDenied,
    StudentRepository,
    redact,
)

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


from business_logic.uma.uma_service import UmaService
from business_logic.siem.student_service import StudentService
from business_logic.amg.scheduling_service import scheduling_service, CapacityLimitError

# ---------------------------------------------------------
# Create FastAPI app FIRST
# ---------------------------------------------------------
app = FastAPI()

# Signed cookie sessions, so the app knows who is logged in. Without this
# the role checks in T1-013 have nobody to check against.
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret(),
    max_age=SESSION_MAX_AGE,
    same_site="lax",
    https_only=False,  # flip to True once T1-008 puts us behind TLS
)

# ---------------------------------------------------------
# Mount static folder (CSS, images, JS)
# ---------------------------------------------------------
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------------------------------------------------------
# Templates setup
# ---------------------------------------------------------
templates = Jinja2Templates(directory="templates")
templates.env.cache = None   # Fixes Jinja2 caching bug
# Classes page: course scheduling UI and teacher assignment (AMG-007 / T1-021, T1-023).
# Its routes live in presentation/classes_routes.py so they don't collide with
# other branches editing this file.
from presentation.classes_routes import router as classes_router
app.include_router(classes_router)

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
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = authenticate(db, username, password)

    if user is not None:
        login_user(request, user)
        logging.info(f"Successful login for user: {username}")
        return RedirectResponse("/dashboard", status_code=302)

    logging.warning(f"Failed login attempt for username: {username}")
    return templates.TemplateResponse(
        request,
        "login.html",
        {"request": request, "error": "Invalid username or password"},
        status_code=401,
    )


@app.get("/logout")
def logout(request: Request):
    logout_user(request)
    return RedirectResponse("/login", status_code=302)


# ---------------------------------------------------------
# DASHBOARD PAGE
# ---------------------------------------------------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    actor = current_actor(request, db)
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)
    # Passing "actor" to the template so it can check roles!
    return templates.TemplateResponse(request, "dashboard.html", {"request": request, "actor": actor})

# ---------------------------------------------------------
# STUDENTS PAGE
# ---------------------------------------------------------
@app.get("/students", response_class=HTMLResponse)
def students_page(request: Request, db: Session = Depends(get_db)):
    actor = current_actor(request, db)
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)

    # Only the students this person may see, with contact details stripped
    # for anyone who shouldn't have them.
    rows = [
        redact(StudentService._to_dict(s), actor, student_user_id=s.user_id)
        for s in StudentRepository(db).list_visible(actor)
    ]
    return templates.TemplateResponse(
        request,
        "students.html",
        {"request": request, "students": rows, "actor": actor}
    )


# ---------------------------------------------------------
# PARENT PORTAL (SIEM-006 / T2-006)
# ---------------------------------------------------------
@app.get("/parent/portal", response_class=HTMLResponse)
def parent_portal(request: Request, db: Session = Depends(get_db)):
    actor = current_actor(request, db)
    
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)
        
    repo = StudentRepository(db)

    # Kick them out if they are logged in but aren't a parent
    if actor.role != "Parent":
        # T2-008. They only get redirected, so without this the attempt
        # leaves no trace anywhere.
        repo.record_portal_refusal(actor)
        return RedirectResponse("/dashboard", status_code=302)

    # Gets only the students this parent is allowed to see.
    children = repo.list_visible(actor)

    # T2-008. Each child shown gets its own line naming them, which is what
    # a FERPA question actually needs.
    repo.record_parent_disclosure(actor, children)

    rows = [
        redact(StudentService._to_dict(s), actor, student_user_id=s.user_id)
        for s in children
    ]
    
    return templates.TemplateResponse(
        request,
        "parent_portal.html",
        {"request": request, "children": rows}
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
def new_student_form(request: Request, db: Session = Depends(get_db)):
    actor = current_actor(request, db)
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)
    if actor.role != "Admin":
        return _denied(request, "Only administrators can enroll students.")

    return templates.TemplateResponse(
        request,
        "student_form.html",
        {"request": request, "form": {}, "errors": {}}
    )


@app.post("/students/new", response_class=HTMLResponse)
async def create_student(request: Request, db: Session = Depends(get_db)):
    actor = current_actor(request, db)
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)
    if actor.role != "Admin":
        logging.warning(
            f"Blocked student create by user {actor.user_id} (role {actor.role})"
        )
        return _denied(request, "Only administrators can enroll students.")

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
from database.models import User, Role

@app.get("/teachers", response_class=HTMLResponse)
def teachers_page(request: Request, db: Session = Depends(get_db)):
    actor = current_actor(request, db)
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)

    teacher_role = db.query(Role).filter(Role.name == "Teacher").first()
    teacher_users = db.query(User).filter(User.role_id == teacher_role.id).all() if teacher_role else []

    # Format the data to match what the template expects
    teacher_list = [
        {"id": t.id, "name": f"{t.first_name} {t.last_name}", "subject": "See classes"}
        for t in teacher_users
    ]

    return templates.TemplateResponse(
        request,
        "teachers.html",
        {"request": request, "teachers": teacher_list}
    )

# ---------------------------------------------------------
# TEACHER PROFILE PAGE
# ---------------------------------------------------------
@app.get("/ui/teacher/{teacher_id}", response_class=HTMLResponse)
def teacher_ui(request: Request, teacher_id: int, db: Session = Depends(get_db)):
    actor = current_actor(request, db)
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)

    teacher_role = db.query(Role).filter(Role.name == "Teacher").first()
    
    # Query for the specific user ID ensuring they are actually a teacher
    user = None
    if teacher_role:
        user = db.query(User).filter(User.id == teacher_id, User.role_id == teacher_role.id).first()

    if not user:
        return templates.TemplateResponse(
            request, 
            "teacher_profile.html", 
            {"request": request, "teacher": None}, 
            status_code=404
        )

    teacher_data = {
        "id": user.id,
        "name": f"{user.first_name} {user.last_name}",
        "subject": "See classes"
    }

    return templates.TemplateResponse(
        request,
        "teacher_profile.html",
        {"request": request, "teacher": teacher_data}
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
def student_ui(request: Request, student_id: str, db: Session = Depends(get_db)):
    actor = current_actor(request, db)
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)

    try:
        sid = int(student_id)
    except (TypeError, ValueError):
        return _not_found(request)

    repo = StudentRepository(db)
    try:
        student = repo.get(actor, sid)
    except LookupError:
        return _not_found(request)
    except AccessDenied:
        # Logged, not silently empty. Someone poking at record ids is worth
        # seeing in the trail (T1-014).
        logging.warning(
            f"Access denied: user {actor.user_id} (role {actor.role}) "
            f"requested student {sid}"
        )
        return _denied(request, "You do not have access to that student record.")

    data = redact(
        StudentService._to_dict(student), actor, student_user_id=student.user_id
    )
    return templates.TemplateResponse(
        request, "student_profile.html", {"request": request, "student": data}
    )


def _denied(request: Request, message: str):
    return templates.TemplateResponse(
        request,
        "student_profile.html",
        {"request": request, "student": None, "error": message},
        status_code=403,
    )


def _not_found(request: Request):
    return templates.TemplateResponse(
        request,
        "student_profile.html",
        {"request": request, "student": None},
        status_code=404,
    )
