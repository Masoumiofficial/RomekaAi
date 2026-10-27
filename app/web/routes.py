from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.deps import SESSION_COOKIE, get_signer
from app.core.security import SessionSigner
from app.db.models import User
from app.db.session import get_db
from pathlib import Path

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
    data = signer.read(request.cookies.get(SESSION_COOKIE, ""))
    if data is None:
        return None
    user = db.query(User).filter(User.id == data.user_id, User.is_active.is_(True)).first()
    return (user, data.csrf) if user else None


def _render(request: Request, page: str, db: Session, signer: SessionSigner):
    ctx = _context(request, db, signer)
    if ctx is None:
        return RedirectResponse("/auth", status_code=303)
    user, csrf = ctx
    title, subtitle = PAGES[page]
    return templates.TemplateResponse(request, f"{page}.html", {
        "page": page, "title": title, "subtitle": subtitle,
        "user": user, "csrf": csrf,
    })


@router.get("/auth", response_class=HTMLResponse)
def auth_page(request: Request):
    return templates.TemplateResponse(request, "auth.html")


def _make(page: str):
    def handler(request: Request, db: Session = Depends(get_db),
                signer: SessionSigner = Depends(get_signer)):
        return _render(request, page, db, signer)
    return handler


for _page in PAGES:
    path = "/" if _page == "dashboard" else f"/{_page}"
    router.add_api_route(path, _make(_page), methods=["GET"], response_class=HTMLResponse,
                         name=f"page_{_page}", include_in_schema=False)
