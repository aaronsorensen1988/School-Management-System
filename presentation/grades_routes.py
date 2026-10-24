from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from business_logic.siem.grade_service import (
    GradeAccessError,
    GradeEntryError,
    GradeService,
)
from business_logic.siem.grade_validation import GradeValidationError, parse_points
from database.database import get_db
from auth.session import current_actor 

router = APIRouter()
templates = Jinja2Templates(directory="templates")

def _entry_page(request, form, error):
    """Grade entry form again, with the T2-014 message and what they typed."""
    return templates.TemplateResponse(
        request, "grade_entry.html", {"form": form, "error": error}, status_code=400
    )


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
    # Taken as text and parsed here (T2-014) so "abc" or a blank box gets a
    # readable message on the page instead of FastAPI's 422 error.
    points_earned: str = Form(""),
    db: Session = Depends(get_db)
):
    # 3. Block unauthorized form submissions
    actor = current_actor(request, db)
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)
        
    form = {"student_id": student_id, "assignment_id": assignment_id,
            "points_earned": points_earned}

    points, problem = parse_points(points_earned)
    if problem:
        return _entry_page(request, form, problem)

    # 1. Check if a grade already exists for this student/assignment combo
    try:
        GradeService.record_grade(
            db,
            actor,
            student_id,
            assignment_id,
            points,
        )
    except GradeValidationError as exc:
        db.rollback()
        return _entry_page(request, form, str(exc))
    except GradeAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except GradeEntryError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return RedirectResponse(url="/grades/entry", status_code=303)