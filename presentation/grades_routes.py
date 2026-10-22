from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database.database import get_db
from database.grades import Grade
from auth.session import current_actor 

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/grades/entry", response_class=HTMLResponse)
def get_grade_entry(request: Request, db: Session = Depends(get_db)):
    # 2. Check login status (Note: added db Session to parameters for this to work)
    actor = current_actor(request, db)
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)
        
    return templates.TemplateResponse(request, "grade_entry.html")

@router.post("/grades/entry")
def post_grade_entry(
    request: Request,
    student_id: int = Form(...),
    assignment_id: int = Form(...),
    points_earned: float = Form(...),
    db: Session = Depends(get_db)
):
    # 3. Block unauthorized form submissions
    actor = current_actor(request, db)
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)
        
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