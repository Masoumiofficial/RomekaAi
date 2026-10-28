from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.deps import extract_session_token, get_signer
from app.config import Settings, get_settings
from app.core.security import SessionSigner
from app.db.models import User
from app.db.session import get_db
from pathlib import Path
from types import SimpleNamespace

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))

PAGES = {
    "dashboard": ("داشبورد", "نمای کلی امروز، اولویتها و وضعیت سیستم"),
    "chat": ("گفتوگو با رومکا", "هسته مرکزی، متخصصها، حافظه و نقد مستقل"),
    "planner": ("برنامهریز", "برنامه واقعبینانه، تداخلها و بازبرنامهریزی"),
    "agents": ("متخصصها", "شبکه متخصصان و نقشه تعاملی آناتومی"),
    "business": ("پروژهها و کسبوکار", "پیشرفت واقعی در برابر مشغولیت"),
    "health": ("سلامت و بدن", "تمرین، تغذیه و ثبت نتایج واقعی"),
    "memory": ("حافظه و اطلاعات", "مشاهده، اصلاح و حذف دادههای ذخیرهشده"),
    "settings": ("تنظیمات سیستم", "مدلها، بودجه، مهارتها، پیامرسانها و امنیت"),
    "onboarding": ("راهاندازی", "اطلاعات اولیه، قابل تکمیل در چند جلسه"),
}


def _context(request: Request, db: Session, signer: SessionSigner):
    data = signer.read(extract_session_token(request))
    if data is None:
        return None
    user = db.query(User).filter(User.id == data.user_id, User.is_active.is_(True)).first()
    return (user, data.csrf) if user else None


# Static HTML shell used when the browser refuses third-party cookies. It holds
# NO user data: every data request still goes through get_auth_context with the
# signed bearer token, and romka.js redirects to /auth when that token is absent.
SHELL_USER = SimpleNamespace(display_name="", email="", timezone="Asia/Tehran")


def _render(request: Request, page: str, db: Session, signer: SessionSigner):
    ctx = _context(request, db, signer)
    if ctx is not None:
        user, csrf = ctx
        auth_mode = "session"
    else:
        user, csrf, auth_mode = SHELL_USER, "", "client"
    title, subtitle = PAGES[page]
    return templates.TemplateResponse(request, f"{page}.html", {
        "page": page, "title": title, "subtitle": subtitle,
        "user": user, "csrf": csrf, "auth_mode": auth_mode,
    })


@router.get("/auth", response_class=HTMLResponse)
def auth_page(request: Request, settings: Settings = Depends(get_settings)):
    """Login page.

    Demo credentials are shown ONLY when startup proved they actually work
    (account created, or existing account whose password matches). Otherwise a
    short notice explains why they are hidden, so nobody is told a wrong password.
    """
    state = getattr(request.app.state, "demo_login", None) or {}
    demo = notice = None
    if state.get("ready"):
        demo = {"email": settings.ROMKA_DEMO_EMAIL,
                "password": settings.ROMKA_DEMO_PASSWORD}
    elif settings.ROMKA_AUTO_DEMO and not settings.is_production:
        notice = state.get("reason") or ("حساب دمو آماده نیست؛ از " 
                                        "«شروع سریع مهمان» استفاده کنید.")
    return templates.TemplateResponse(request, "auth.html",
                                      {"demo_login": demo, "demo_notice": notice})


def _make(page: str):
    def handler(request: Request, db: Session = Depends(get_db),
                signer: SessionSigner = Depends(get_signer)):
        return _render(request, page, db, signer)
    return handler


for _page in PAGES:
    path = "/" if _page == "dashboard" else f"/{_page}"
    router.add_api_route(path, _make(_page), methods=["GET"], response_class=HTMLResponse,
                         name=f"page_{_page}", include_in_schema=False)
