"""Emergency notifications page. CNS-012 / T2-030 (UI) and T2-031 (broadcast). Shanna.

  GET  /emergency               everyone: their alerts, unread ones first in red
                                admin: also the send form and what's been sent
  POST /emergency               admin only: send an alert
  POST /emergency/{id}/read     mark one of your alerts read

The dashboard shows a red banner while someone has unread alerts.

Own router, same as the other pages, so api.py only needs one include line.
"""

import logging
from datetime import timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from auth.session import current_actor
from business_logic.siem import emergency_service
from business_logic.siem.emergency_service import AUDIENCE_LABELS, EmergencyAccessError
from database.announcements import AUDIENCES
from database.database import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.cache = None


def local_time(value, fmt="%b %d, %Y %I:%M %p"):
    """Show a saved time in the server's local time zone.

    Times are saved in UTC. SQLite hands them back without a time zone, so
    without this an alert sent at 7:53 PM Pacific showed as 02:53 AM.
    """
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone().strftime(fmt)


templates.env.filters["local_time"] = local_time

NOTICES = {"sent": "Emergency alert sent."}


def _render(request, db, actor, status_code=200, errors=None, form=None, message=None, notice=None):
    is_admin = actor.role == "Admin"
    context = {
        "request": request,
        "is_admin": is_admin,
        "alerts": emergency_service.inbox(db, actor.user_id),
        "history": emergency_service.sent_history(db) if is_admin else [],
        "audiences": [(a, AUDIENCE_LABELS[a]) for a in AUDIENCES],
        "audience_labels": AUDIENCE_LABELS,
        "title_max": emergency_service.TITLE_MAX,
        "message_max": emergency_service.MESSAGE_MAX,
        "errors": errors or {},
        "form": form or {},
        "message": message,
        "notice": notice,
    }
    return templates.TemplateResponse(request, "emergency.html", context, status_code=status_code)


@router.get("/emergency", response_class=HTMLResponse)
def emergency_page(request: Request, db: Session = Depends(get_db)):
    actor = current_actor(request, db)
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)
    return _render(request, db, actor, notice=NOTICES.get(request.query_params.get("notice", "")))


@router.post("/emergency", response_class=HTMLResponse)
async def send_alert(request: Request, db: Session = Depends(get_db)):
    actor = current_actor(request, db)
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)

    form = dict(await request.form())
    try:
        _, errors = emergency_service.send_emergency(db, actor, form)
    except EmergencyAccessError as exc:
        logging.warning(f"Blocked emergency alert by user {actor.user_id} (role {actor.role})")
        return _render(request, db, actor, status_code=403, message=str(exc))

    if errors:
        return _render(request, db, actor, status_code=400, errors=errors, form=form)
    return RedirectResponse("/emergency?notice=sent", status_code=303)


@router.post("/emergency/{notification_id}/read")
def read_alert(notification_id: int, request: Request, db: Session = Depends(get_db)):
    actor = current_actor(request, db)
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)
    if not emergency_service.mark_read(db, actor.user_id, notification_id):
        return _render(request, db, actor, status_code=404, message="Alert not found.")
    return RedirectResponse("/emergency", status_code=303)
