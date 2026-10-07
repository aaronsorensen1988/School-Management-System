print(">>> RUNNING CORRECT API.PY <<<")

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

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

# ---------------------------------------------------------
# LOGIN ROUTES
# ---------------------------------------------------------
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"request": request})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == "admin" and password == "password123":
        return RedirectResponse("/dashboard", status_code=302)
    else:
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
        {"request": request, "students": students}
    )

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
    profile = uma.get_user_profile(student_id)
    return templates.TemplateResponse(
        request,
        "student_profile.html",
        {
            "request": request,
            "profile": profile
        }
    )
