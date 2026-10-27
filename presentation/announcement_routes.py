from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from auth.session import current_actor
from database.database import get_db
from database.announcements import Announcement, AUDIENCES
from business_logic.siem.announcement_service import (
    AnnouncementService,
    AnnouncementAccessError,
)
from business_logic.uma.access_control import AccessControl

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/announcements", response_class=HTMLResponse)
def announcements_home(request: Request, db: Session = Depends(get_db)):
    actor = current_actor(request, db)
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)
        
    can_post = AccessControl.can_post_announcement(actor.role)
    
    # Fetch all published announcements, ordered newest first
    all_published = db.query(Announcement).filter(
        Announcement.published_at.is_not(None)
    ).order_by(Announcement.published_at.desc()).all()
    
    # Filter to only what this user's role is allowed to see
    visible_announcements = [a for a in all_published if a.is_visible_to(actor.role)]
    
    return templates.TemplateResponse(
        request, 
        "announcements.html", 
        {
            "can_post": can_post, 
            "announcements": visible_announcements
        }
    )

@router.get("/announcements/new", response_class=HTMLResponse)
def new_announcement_form(request: Request, db: Session = Depends(get_db)):
    actor = current_actor(request, db)
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)
        
    # Block unauthorized users from seeing the form
    if not AccessControl.can_post_announcement(actor.role):
        raise HTTPException(
            status_code=403, 
            detail="Only authorized staff may post announcements."
        )
        
    return templates.TemplateResponse(
        request, 
        "announcement_form.html", 
        {"audiences": AUDIENCES}
    )

@router.post("/announcements/new")
def create_announcement(
    request: Request, 
    title: str = Form(...),
    body: str = Form(...),
    audience: str = Form(...),
    db: Session = Depends(get_db)
):
    actor = current_actor(request, db)
    if actor.role is None:
        return RedirectResponse("/login", status_code=302)
        
    try:
        # 1. Create the draft
        draft = AnnouncementService.create_draft(
            db=db,
            actor=actor,
            title=title,
            body=body,
            audience=audience
        )
        
        # 2. Publish it
        AnnouncementService.publish(
            db=db,
            actor=actor,
            announcement_id=draft.id
        )
    except AnnouncementAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
        
    return RedirectResponse(url="/announcements", status_code=303)