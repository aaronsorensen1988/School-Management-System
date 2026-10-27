"""Report card page. AMG-009 / T2-016 (report card generator). Shanna.

Builds a student's report card from T2-019's grade_aggregation: a grade and
letter for each class, an overall average, and attendance totals.

  GET /report-cards              admin: list of students to pick from
                                 student: sent straight to their own card
  GET /report-cards/{user id}    one student's report card

Who can see what (AMG-009: "students/parents view only their own"):
  - Admin: any student
  - Student: only their own
  - Everyone else, for now: 403. Parents seeing their child's card is
    T2-018, and print/PDF formatting is T2-017.

Own router, same as the classes and attendance pages, so api.py only needs
one include line.
"""

import logging
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from auth.session import current_actor
from business_logic.amg.grade_aggregation import student_report
from database.database import get_db
from database.models import Role, User

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.cache = None


def can_view_report_card(actor, student_user_id):
    """Admins see any report card, students only their own."""
    if actor.role == "Admin":
        return True
    if actor.role == "Student":
        return actor.user_id == student_user_id
    return False


def _students(db):
    return (
        db.query(User)
        .join(Role, Role.id == User.role_id)
        .filter(Role.name == "Student")
        .order_by(User.last_name, User.first_name)
        .all()
    )


def _render(request, context, status_code=200):
    base = {"request": request, "student": None, "report": None, "students": [], "message": None}
    base.update(context)
    return templates.TemplateResponse(request, "report_card.html", base, status_code=status_code)


@router.get("/report-cards", response_class=HTMLResponse)
def report_cards_home(request: Request, db: Session = Depends(get_db)):
    actor = current_actor(request, db)
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)
    if actor.role == "Student":
        return RedirectResponse(f"/report-cards/{actor.user_id}", status_code=302)
    if actor.role != "Admin":
        logging.warning(f"Blocked report card list by user {actor.user_id} (role {actor.role})")
        return _render(request, {"message": "Report cards are only available to administrators and students."},
                       status_code=403)
    students = [{"id": s.id, "name": f"{s.first_name} {s.last_name}"} for s in _students(db)]
    return _render(request, {"students": students})


@router.get("/report-cards/{student_id}", response_class=HTMLResponse)
def report_card(student_id: int, request: Request, db: Session = Depends(get_db)):
    actor = current_actor(request, db)
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)

    # Check permission before looking the student up, so someone without
    # access can't tell which ids belong to real students.
    if not can_view_report_card(actor, student_id):
        logging.warning(f"Blocked report card view by user {actor.user_id} (role {actor.role}) for student {student_id}")
        return _render(request, {"message": "You can only view your own report card."}, status_code=403)

    student = (
        db.query(User)
        .join(Role, Role.id == User.role_id)
        .filter(User.id == student_id, Role.name == "Student")
        .first()
    )
    if student is None:
        return _render(request, {"message": "Student not found."}, status_code=404)

    return _render(request, {
        "student": {"id": student.id, "name": f"{student.first_name} {student.last_name}"},
        "report": student_report(db, student.id),
        "generated_on": date.today().strftime("%B %d, %Y").replace(" 0", " "),
        "is_admin": actor.role == "Admin",
    })
