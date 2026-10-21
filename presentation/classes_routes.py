"""Classes page: course scheduling UI and teacher assignment.
AMG-007 / T1-021 (UI) and T1-023 (teacher assignment). Shanna.

These routes live in their own router instead of api.py so they don't
collide with the other Sprint 2 branches that are editing api.py.
api.py only needs one include_router line.

Who can do what:
  - Admin: sees every section, adds courses and sections, assigns teachers
  - Teacher: sees only the sections they teach
  - Student: sees only the sections they're enrolled in
  - Not logged in: sent to /login
"""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from auth.session import current_actor
from business_logic.amg import schedule_service
from business_logic.amg.teacher_assignment import (
    TeacherAssignmentError,
    assign_teacher,
    list_teachers,
    unassign_teacher,
)
from database.database import get_db
from database.scheduling import DAYS, DEFAULT_CAPACITY, Course

router = APIRouter()

# Success messages are picked from this list by key, so the page never
# echoes whatever text someone puts in the URL.
NOTICES = {
    "course_added": "Course added.",
    "section_added": "Section added.",
    "teacher_assigned": "Teacher assigned.",
    "teacher_removed": "Teacher removed from the section.",
}
templates = Jinja2Templates(directory="templates")
templates.env.cache = None


def _render(request, db, actor, status_code=200, errors=None, form=None, message=None, notice=None):
    is_admin = actor.role == "Admin"
    context = {
        "request": request,
        "actor": actor,
        "is_admin": is_admin,
        "sections": [schedule_service.section_row(s) for s in schedule_service.sections_for(db, actor)],
        "courses": db.query(Course).order_by(Course.code).all() if is_admin else [],
        "teachers": [
            {"id": t.id, "name": f"{t.first_name} {t.last_name}"} for t in list_teachers(db)
        ] if is_admin else [],
        "days": DAYS,
        "default_capacity": DEFAULT_CAPACITY,
        "errors": errors or {},
        "form": form or {},
        "message": message,
        "notice": notice,
    }
    return templates.TemplateResponse(request, "classes.html", context, status_code=status_code)


def _admin_only(request, db, actor):
    """None if the user may change the schedule, otherwise the response to send."""
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)
    if actor.role != "Admin":
        logging.warning(f"Blocked schedule change by user {actor.user_id} (role {actor.role})")
        return _render(request, db, actor, status_code=403,
                       message="Only administrators can change the class schedule.")
    return None


@router.get("/classes", response_class=HTMLResponse)
def classes_page(request: Request, db: Session = Depends(get_db)):
    actor = current_actor(request, db)
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)
    notice = NOTICES.get(request.query_params.get("notice", ""))
    return _render(request, db, actor, notice=notice)


@router.post("/classes/courses", response_class=HTMLResponse)
async def add_course(request: Request, db: Session = Depends(get_db)):
    actor = current_actor(request, db)
    blocked = _admin_only(request, db, actor)
    if blocked:
        return blocked

    form = dict(await request.form())
    _, errors = schedule_service.create_course(db, form)
    if errors:
        return _render(request, db, actor, status_code=400,
                       errors={f"course_{k}": v for k, v in errors.items()}, form=form)
    return RedirectResponse("/classes?notice=course_added", status_code=303)


@router.post("/classes/sections", response_class=HTMLResponse)
async def add_section(request: Request, db: Session = Depends(get_db)):
    actor = current_actor(request, db)
    blocked = _admin_only(request, db, actor)
    if blocked:
        return blocked

    form = dict(await request.form())
    _, errors = schedule_service.create_section(db, form)
    if errors:
        return _render(request, db, actor, status_code=400,
                       errors={f"section_{k}": v for k, v in errors.items()}, form=form)
    return RedirectResponse("/classes?notice=section_added", status_code=303)


@router.post("/classes/{section_id}/teacher", response_class=HTMLResponse)
async def set_teacher(section_id: int, request: Request, db: Session = Depends(get_db)):
    actor = current_actor(request, db)
    blocked = _admin_only(request, db, actor)
    if blocked:
        return blocked

    form = dict(await request.form())
    raw = str(form.get("teacher_id") or "").strip()
    try:
        if raw == "":
            unassign_teacher(db, section_id)
            notice = "teacher_removed"
        else:
            assign_teacher(db, section_id, int(raw))
            notice = "teacher_assigned"
    except LookupError as e:
        return _render(request, db, actor, status_code=404, message=str(e))
    except (TeacherAssignmentError, ValueError) as e:
        db.rollback()
        return _render(request, db, actor, status_code=400, message=str(e))

    return RedirectResponse(f"/classes?notice={notice}", status_code=303)
