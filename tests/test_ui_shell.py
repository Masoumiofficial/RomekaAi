"""The visual shell is a feature: Persian-first type, RTL layout, no page that
scrolls sideways on a phone. These checks keep a redesign from quietly breaking
the accessibility and responsiveness rules the product promises."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app" / "web" / "static" / "css" / "romka.css").read_text(encoding="utf-8")
BASE = (ROOT / "app" / "web" / "templates" / "base.html").read_text(encoding="utf-8")
JS = (ROOT / "app" / "web" / "static" / "js" / "romka.js").read_text(encoding="utf-8")
PAGES = ["dashboard", "chat", "planner", "agents", "business", "health", "memory",
         "settings", "onboarding"]


def test_persian_font_ships_locally_with_its_license():
    """A pretty UI must not depend on a CDN, and the font keeps its attribution."""
    fonts = ROOT / "app" / "web" / "static" / "fonts"
    for name in ("vazirmatn-arabic-400-normal.woff2", "vazirmatn-arabic-500-normal.woff2",
                 "vazirmatn-arabic-700-normal.woff2", "vazirmatn-latin-400-normal.woff2"):
        assert (fonts / name).is_file(), f"{name} missing from the bundle"
        assert (fonts / name).stat().st_size > 1000
    license_text = (fonts / "Vazirmatn-LICENSE.txt").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE" in license_text
    # every @font-face src is served from our own static folder
    for src in re.findall(r'src:\s*url\("([^"]+)"\)', CSS):
        assert src.startswith("/static/fonts/"), src
    assert "Vazirmatn" in CSS and "--ff:" in CSS
    # no external font/CDN request anywhere in the stylesheet
    assert "http://" not in CSS and "https://" not in CSS


def test_type_scale_uses_only_shipped_weights():
    """Weights we do not ship would be faked by the browser and look uneven."""
    weights = {int(w) for w in re.findall(r"font-weight:\s*(\d+)", CSS)}
    assert weights <= {400, 500, 700}, weights


def test_every_page_is_reachable_and_has_the_accessible_shell(client):
    for page in PAGES:
        body = client.get("/" if page == "dashboard" else f"/{page}")
        assert body.status_code == 200, f"{page} returned {body.status_code}"
        text = body.text
        assert 'id="main-content"' in text, f"{page}: skip-link target missing"
        assert 'class="skip-link"' in text, f"{page}: skip link missing"
        assert 'aria-label="ناوبری اصلی"' in text, f"{page}: sidebar not labelled"
        assert 'aria-current="page"' in text, f"{page}: active page not announced"
        assert 'id="sidebar-backdrop"' in text, f"{page}: mobile drawer backdrop missing"
        # RTL and a responsive viewport are preconditions for the design
        assert 'dir="rtl"' in text and 'name="viewport"' in text
        # cache-busting: every local script carries the app version
        for src in re.findall(r'<script src="(/static/js/[^"]+)"', text):
            assert "?v=" in src, f"{page}: {src} is not versioned"
    assert "romka.css?v=0.2.20" in client.get("/").text
    assert client.get("/static/css/romka.css").status_code == 200
    assert client.get("/static/fonts/vazirmatn-arabic-400-normal.woff2").status_code == 200


def test_mobile_menu_is_keyboard_and_pointer_safe():
    """The drawer must be closable with a keyboard and must not trap focus."""
    assert 'id="menu-btn"' in BASE and 'aria-controls="sidebar"' in BASE
    assert 'aria-expanded="false"' in BASE
    assert "setMenu" in JS and "Escape" in JS
    assert 'backdrop' in JS and "innerWidth" in JS  # closes on resize to desktop
    # the drawer never relies on a JS-only close: it is a plain toggle class
    assert 'classList.toggle("open")' in JS or 'classList.toggle("open", open)' in JS


def test_grids_cannot_force_horizontal_scrolling():
    """minmax(0,1fr) is what stops a long task row from widening the page."""
    for selector in (".g-2", ".g-3", ".g-4", ".g-main", ".grid-form", ".auth-wrap"):
        assert f".{selector.strip('.')}" in CSS
    assert CSS.count("grid-template-columns: minmax(0,1fr)") >= 3
    # long Persian words and Latin identifiers must wrap instead of overflowing
    assert "overflow-wrap:anywhere" in CSS
    # a reduced-motion user gets no animation
    assert "prefers-reduced-motion" in CSS


def test_light_theme_keeps_contrast_tokens():
    """Both themes must redefine the same variables, or half the UI stays dark."""
    dark = set(re.findall(r"--([a-z0-9-]+):", CSS.split(":root", 1)[1].split("}", 1)[0]))
    light = set(re.findall(r"--([a-z0-9-]+):",
                            "}".join(part.split("}", 1)[0] for part in
                                     CSS.split("html[data-theme=\"light\"]")[1:])))
    assert {"bg", "surface", "text", "muted", "accent", "border"} <= light
    assert {"accent", "surface"} <= dark


@pytest.mark.parametrize("page", PAGES)
def test_pages_do_not_ship_broken_inline_styles(client, page):
    """Guards against a leftover width that only shows on small screens."""
    text = client.get("/" if page == "dashboard" else f"/{page}").text
    for width in re.findall(r'(?<!max-)width:\s*(\d{3,})px', text):
        assert int(width) <= 400, f"{page}: fixed width {width}px is not responsive"
