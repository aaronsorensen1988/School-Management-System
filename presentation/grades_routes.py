from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database.database import get_db
from database.grades import Grade

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/grades/entry", response_class=HTMLResponse)
def get_grade_entry(request: Request):
    return templates.TemplateResponse(request, "grade_entry.html")

@router.post("/grades/entry")
def post_grade_entry(
    request: Request,
    student_id: int = Form(...),
    assignment_id: int = Form(...),
    points_earned: float = Form(...),
    db: Session = Depends(get_db)
):
    # 1. Check if a grade already exists for this student/assignment combo
    existing_grade = db.query(Grade).filter(
        Grade.student_id == student_id,
        Grade.assignment_id == assignment_id
    ).first()
    
    if existing_grade:
        # 2. If it exists, update the score
        existing_grade.points_earned = points_earned
    else:
        # 3. If it doesn't exist, create a new row
        new_grade = Grade(
            student_id=student_id,
            assignment_id=assignment_id,
            points_earned=points_earned
        )
        db.add(new_grade)
        
    db.commit()
    
    return RedirectResponse(url="/grades/entry", status_code=303)