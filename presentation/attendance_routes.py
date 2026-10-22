"""Attendance page. SIEM-005 / T2-001 (entry UI) and T2-004 (validation). Shanna.

Own router, same as the classes page, so api.py only needs one include line.

  GET  /attendance                   list of sections you can take attendance for
  GET  /attendance/{id}?date=...     the roster for one day
  POST /attendance/{id}              save the whole roster for that day

Who can do what:
  - Teacher: their own sections, can save (T2-003 rule)
  - Admin: every section, view only
  - Anyone else: 403
  - Not logged in: sent to /login
"""

import logging
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from auth.session import current_actor
from business_logic.amg import schedule_service
from business_logic.siem import attendance_entry
from business_logic.siem.attendance_service import AttendanceAccessError
from business_logic.siem.attendance_validation import NOTE_MAX, parse_date
from database.attendance import PRESENT, STATUSES
from database.database import get_db
from database.scheduling import DAYS, Section

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.cache = None

NOTICES = {"saved": "Attendance saved."}


def _render(request, context, status_code=200):
    base = {"request": request, "statuses": STATUSES, "note_max": NOTE_MAX,
            "section": None, "sections": [], "errors": {}, "message": None, "notice": None}
    base.update(context)
    return templates.TemplateResponse(request, "attendance.html", base, status_code=status_code)


def _roster_rows(db, section, on_date, submitted=None):
    """One dict per student for the template, filled from what's saved or what was just submitted."""
    saved = attendance_entry.existing_for_day(db, section.id, on_date) if on_date else {}
    rows = []
    for student in attendance_entry.roster(db, section.id):
        if submitted is not None:
            status, note = submitted.get(student.id, ("", ""))
        elif student.id in saved:
            status, note = saved[student.id].status, saved[student.id].note or ""
        else:
            status, note = PRESENT, ""
        rows.append({"id": student.id, "name": f"{student.first_name} {student.last_name}",
                     "status": status, "note": note, "recorded": student.id in saved})
    return rows


def _section_or_block(request, db, actor, section_id):
    """(section, None) if this user may see it, otherwise (None, response)."""
    if actor.role is None:
        return None, RedirectResponse("/login", status_code=302)
    section = db.query(Section).filter(Section.id == section_id).first()
    if section is None:
        return None, _render(request, {"message": "Class not found."}, status_code=404)
    if not attendance_entry.can_view(actor, section):
        logging.warning(f"Blocked attendance view by user {actor.user_id} (role {actor.role}) for section {section_id}")
        return None, _render(request, {"message": "You can only take attendance for classes you teach."}, status_code=403)
    return section, None


@router.get("/attendance", response_class=HTMLResponse)
def attendance_home(request: Request, db: Session = Depends(get_db)):
    actor = current_actor(request, db)
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)
    if actor.role not in ("Teacher", "Admin"):
        return _render(request, {"message": "Only teachers and administrators can use the attendance page."},
                       status_code=403)
    sections = attendance_entry.sections_for(db, actor)
    day_order = {d: i for i, d in enumerate(DAYS)}
    sections.sort(key=lambda s: (day_order.get(s.day_of_week, 99), s.start_time, s.room))
    return _render(request, {"sections": [schedule_service.section_row(s) for s in sections],
                             "is_admin": actor.role == "Admin"})


@router.get("/attendance/{section_id}", response_class=HTMLResponse)
def attendance_day(section_id: int, request: Request, db: Session = Depends(get_db)):
    actor = current_actor(request, db)
    section, blocked = _section_or_block(request, db, actor, section_id)
    if blocked:
        return blocked

    errors = {}
    raw = request.query_params.get("date")
    if raw:
        on_date, problem = parse_date(raw)
        if problem:
            errors["date"] = problem
            on_date = attendance_entry.default_date(section)
    else:
        on_date = attendance_entry.default_date(section)

    return _render(request, {
        "section": schedule_service.section_row(section),
        "on_date": on_date.isoformat(),
        "today": date.today().isoformat(),
        "can_save": attendance_entry.can_take(actor, section),
        "rows": _roster_rows(db, section, on_date),
        "errors": errors,
        "notice": NOTICES.get(request.query_params.get("notice", "")),
    })


@router.post("/attendance/{section_id}", response_class=HTMLResponse)
async def save_attendance(section_id: int, request: Request, db: Session = Depends(get_db)):
    actor = current_actor(request, db)
    section, blocked = _section_or_block(request, db, actor, section_id)
    if blocked:
        return blocked

    form = await request.form()
    on_date, date_problem = parse_date(form.get("on_date"))

    # status_<student id> and note_<student id> for each row
    entries = {}
    for key in form.keys():
        if key.startswith("status_"):
            try:
                student_id = int(key[len("status_"):])
            except ValueError:
                continue
            entries[student_id] = (str(form.get(key) or ""), str(form.get(f"note_{student_id}") or ""))

    def again(errors, status_code):
        return _render(request, {
            "section": schedule_service.section_row(section),
            "on_date": str(form.get("on_date") or ""),
            "today": date.today().isoformat(),
            "can_save": attendance_entry.can_take(actor, section),
            "rows": _roster_rows(db, section, on_date, submitted=entries),
            "errors": errors,
            "message": "Nothing was saved. Fix the items marked below and try again.",
        }, status_code=status_code)

    try:
        if date_problem:
            if not attendance_entry.can_take(actor, section):
                raise AttendanceAccessError("not allowed")
            return again({"date": date_problem}, 400)
        _, errors = attendance_entry.save_roster(db, actor, section, on_date, entries)
    except AttendanceAccessError:
        logging.warning(f"Blocked attendance save by user {actor.user_id} (role {actor.role}) for section {section_id}")
        return _render(request, {"message": "Only the teacher assigned to this class can record attendance."},
                       status_code=403)

    if errors:
        db.rollback()
        return again(errors, 400)

    return RedirectResponse(f"/attendance/{section_id}?date={on_date.isoformat()}&notice=saved", status_code=303)
