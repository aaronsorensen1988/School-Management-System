"""Teacher parent messaging pages. CNS-011 / T2-025.

Three pages. The inbox, one conversation, and the form post that adds to it.

All the rules live in MessagingService, so these do as little as possible:
work out who's asking, hand the request over, and turn whatever comes back
into a page. The one thing they add is the audit row, because a refusal is
only visible here. The service raises, so the route is the only place that
knows the attempt happened at all.
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from auth.session import current_actor
from business_logic.cns import messaging_audit
from business_logic.cns.messaging_inbox import contacts_for, may_send, threads_for
from business_logic.cns.messaging_service import (
    MessagingAccessError,
    MessagingNotFoundError,
    MessagingService,
    MessagingValidationError,
)
from database.database import get_db
from database.models import User
from database.students import Student

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Everybody else gets a 403. Admins included, deliberately. CNS-011 is a
# teacher and parent conversation, and an admin reading it silently is the
# thing the audit log exists to prevent.
MESSAGING_ROLES = ("Teacher", "Parent")


@router.get("/messages", response_class=HTMLResponse)
def inbox(request: Request, db: Session = Depends(get_db)):
    actor = current_actor(request, db)
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)

    if actor.role not in MESSAGING_ROLES:
        messaging_audit.record_refusal(
            db, actor, None, f"{actor.role} opened the messaging inbox"
        )
        raise HTTPException(
            status_code=403,
            detail="Only teachers and parents may use messaging.",
        )

    threads = threads_for(db, actor)
    messaging_audit.record_inbox_listed(db, actor, len(threads))

    # Someone a thread already exists with shouldn't show up twice.
    existing = {(t.other_user.id, t.student.id) for t in threads}

    return templates.TemplateResponse(
        request,
        "messages.html",
        {
            "threads": threads,
            "contacts": [
                c for c in contacts_for(db, actor)
                if (c.other_user.id, c.student.id) not in existing
            ],
            # Parents can't open a conversation, so the page says so instead
            # of leaving an empty space that looks like a bug.
            "is_parent": actor.role == "Parent",
        },
    )


@router.get("/messages/{other_user_id}/{student_id}", response_class=HTMLResponse)
def thread(
    other_user_id: int,
    student_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    actor = current_actor(request, db)
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)

    return _render_thread(request, db, actor, other_user_id, student_id)


@router.post("/messages/{other_user_id}/{student_id}")
def send(
    other_user_id: int,
    student_id: int,
    request: Request,
    body: str = Form(...),
    db: Session = Depends(get_db),
):
    actor = current_actor(request, db)
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)

    try:
        message = MessagingService.send_message(
            db=db,
            actor=actor,
            recipient_id=other_user_id,
            student_id=student_id,
            body=body,
        )
    except MessagingAccessError as exc:
        messaging_audit.record_refusal(db, actor, student_id, str(exc))
        raise HTTPException(status_code=403, detail=str(exc))
    except MessagingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except MessagingValidationError as exc:
        # Back to the conversation with the complaint on it rather than an
        # error page, so a 4000 character overrun doesn't lose the thread.
        return _render_thread(
            request, db, actor, other_user_id, student_id, error=str(exc), status=400
        )

    messaging_audit.record_sent(db, actor, message)

    return RedirectResponse(
        url=f"/messages/{other_user_id}/{student_id}", status_code=303
    )


def _render_thread(request, db, actor, other_user_id, student_id, error=None, status=200):
    """Shared by the GET and by a rejected send, so a failed post comes back
    with the conversation still on the page."""
    try:
        messages = MessagingService.conversation(
            db=db,
            actor=actor,
            other_user_id=other_user_id,
            student_id=student_id,
        )
    except MessagingAccessError as exc:
        messaging_audit.record_refusal(db, actor, student_id, str(exc))
        raise HTTPException(status_code=403, detail=str(exc))
    except MessagingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    messaging_audit.record_thread_viewed(
        db, actor, other_user_id, student_id, len(messages)
    )

    other_user = db.query(User).filter(User.id == other_user_id).first()
    student = db.query(Student).filter(Student.id == student_id).first()

    return templates.TemplateResponse(
        request,
        "message_thread.html",
        {
            "messages": messages,
            "other_user": other_user,
            "student": student,
            "me": actor.user_id,
            "can_send": may_send(actor, other_user_id, messages),
            "error": error,
        },
        status_code=status,
    )
