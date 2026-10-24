from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from business_logic.siem.grade_service import (
    GradeAccessError,
    GradeEntryError,
    GradeService,
)
from database.database import get_db
from auth.session import current_actor 

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/grades/entry", response_class=HTMLResponse)
def get_grade_entry(request: Request, db: Session = Depends(get_db)):
    actor = current_actor(request, db)

    if actor.role is None:
        return RedirectResponse("/login", status_code=302)

    if actor.role != "Teacher":
        raise HTTPException(
            status_code=403,
            detail="Only teachers may access grade entry.",
        )

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
    try:
        GradeService.record_grade(
            db,
            actor,
            student_id,
            assignment_id,
            points_earned,
        )
    except GradeAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except GradeEntryError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return RedirectResponse(url="/grades/entry", status_code=303)