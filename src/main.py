import sys
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

sys.path.append(str(Path(__file__).parent.parent))

from src.app.api.auth_pages import router as auth_page_router
from src.app.api.organizations import api_router, page_router
from src.app.config import settings
from src.app.database import engine
from src.app.services.auth import resolve_auth_user_from_session_cookie
from src.app.services.csrf import ensure_request_csrf_token, validate_request_csrf
from src.app.services.logotypes_batch import close_logo_cache

app = FastAPI()

static_dir = Path(__file__).resolve().parent / "app" / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

_PUBLIC_PATHS = {
    "/",
    "/login",
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
}
_PUBLIC_PREFIXES = ("/static/",)
_AUTH_OPTIONAL_PUBLIC_PATHS = {"/", "/login"}
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _is_public_path(path: str) -> bool:
    return path in _PUBLIC_PATHS or any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES)


def _build_login_redirect(request: Request) -> RedirectResponse:
    next_path = request.url.path
    if request.url.query:
        next_path = f"{next_path}?{request.url.query}"
    return RedirectResponse(
        url=f"/login?next={quote(next_path, safe='')}",
        status_code=303,
    )


def _set_csrf_cookie(response, csrf_token: str) -> None:
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        samesite="lax",
        secure=settings.AUTH_COOKIE_SECURE,
        path="/",
    )


@app.middleware("http")
async def auth_session_middleware(request: Request, call_next):
    request.state.current_user = None
    request.state.can_edit = False
    request.state.csrf_token, csrf_cookie_needs_refresh = ensure_request_csrf_token(request)
    is_public_path = _is_public_path(request.url.path)

    if (not is_public_path) or request.url.path in _AUTH_OPTIONAL_PUBLIC_PATHS:
        request.state.current_user = await resolve_auth_user_from_session_cookie(request)
        request.state.can_edit = bool(
            request.state.current_user is not None and request.state.current_user.can_edit
        )

    if not is_public_path and request.state.current_user is None:
        if request.url.path.startswith("/api/") or request.method != "GET":
            auth_response: Response = JSONResponse(
                {"detail": "Требуется авторизация."},
                status_code=401,
            )
            _set_csrf_cookie(auth_response, request.state.csrf_token)
            return auth_response

        redirect_response = _build_login_redirect(request)
        redirect_response.delete_cookie(
            key=settings.AUTH_COOKIE_NAME,
            httponly=True,
            samesite="lax",
            secure=settings.AUTH_COOKIE_SECURE,
            path="/",
        )
        _set_csrf_cookie(redirect_response, request.state.csrf_token)
        return redirect_response

    requires_csrf = (
        request.method not in _SAFE_METHODS
        and request.url.path not in {"/logout"}
        and (not is_public_path and request.state.current_user is not None)
    )
    if requires_csrf:
        is_valid_csrf = validate_request_csrf(
            request,
            cookie_token=request.state.csrf_token,
        )
        if not is_valid_csrf:
            csrf_response: Response = (
                JSONResponse({"detail": "CSRF validation failed."}, status_code=403)
                if request.url.path.startswith("/api/")
                else PlainTextResponse("CSRF validation failed.", status_code=403)
            )
            _set_csrf_cookie(csrf_response, request.state.csrf_token)
            return csrf_response

    response = await call_next(request)
    if csrf_cookie_needs_refresh or not request.cookies.get(settings.CSRF_COOKIE_NAME):
        _set_csrf_cookie(response, request.state.csrf_token)
    return response


app.include_router(auth_page_router)
app.include_router(page_router)
app.include_router(api_router)


@app.on_event("shutdown")
async def close_resources():
    await close_logo_cache()
    await engine.dispose()
