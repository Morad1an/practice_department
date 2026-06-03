from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from src.app.api.organizations_common import templates
from src.app.config import settings
from src.app.database import async_session_maker
from src.app.services.auth import (
    authenticate_user,
    build_session_cookie_value,
    resolve_safe_next_path,
)
from src.app.services.csrf import validate_submitted_csrf_token

router = APIRouter(tags=["Auth Pages"])


def _set_auth_cookie(response: RedirectResponse, *, user_id: int) -> None:
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=build_session_cookie_value(user_id),
        max_age=settings.AUTH_SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=settings.AUTH_COOKIE_SECURE,
        path="/",
    )


def _clear_auth_cookie(response: RedirectResponse) -> None:
    response.delete_cookie(
        key=settings.AUTH_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=settings.AUTH_COOKIE_SECURE,
        path="/",
    )


@router.get("/", include_in_schema=False)
async def root_redirect(request: Request):
    if getattr(request.state, "current_user", None) is not None:
        return RedirectResponse(url="/organizations/active", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/login", response_class=HTMLResponse, name="login_page")
async def login_page(request: Request, next: str | None = None):
    if getattr(request.state, "current_user", None) is not None:
        return RedirectResponse(
            url=resolve_safe_next_path(next),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return templates.TemplateResponse(
        request,
        "auth/login.html",
        {
            "next_path": resolve_safe_next_path(next),
            "login_error": None,
            "username_value": "",
        },
    )


@router.post("/login", response_class=HTMLResponse, name="login_submit")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str | None = Form(default=None),
    csrf_token: str = Form(...),
):
    safe_next_path = resolve_safe_next_path(next)
    if not validate_submitted_csrf_token(
        csrf_token,
        cookie_token=request.cookies.get(settings.CSRF_COOKIE_NAME),
    ):
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {
                "next_path": safe_next_path,
                "login_error": "Сессия формы устарела. Обновите страницу и попробуйте снова.",
                "username_value": username,
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )

    async with async_session_maker() as session:
        user = await authenticate_user(
            session,
            username=username,
            password=password,
        )

    if user is None:
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {
                "next_path": safe_next_path,
                "login_error": "Неверный логин или пароль.",
                "username_value": username,
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    response = RedirectResponse(url=safe_next_path, status_code=status.HTTP_303_SEE_OTHER)
    _set_auth_cookie(response, user_id=user.id)
    return response


@router.post("/logout", name="logout_page")
async def logout_submit(
    request: Request,
    csrf_token: str = Form(...),
):
    if not validate_submitted_csrf_token(
        csrf_token,
        cookie_token=request.cookies.get(settings.CSRF_COOKIE_NAME),
    ):
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    _clear_auth_cookie(response)
    return response
