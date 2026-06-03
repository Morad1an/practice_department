from src.app.config import settings
from src.app.services.csrf import build_csrf_token


def attach_csrf(client) -> dict[str, str]:
    token = build_csrf_token()
    client.cookies.set(settings.CSRF_COOKIE_NAME, token)
    return {"X-CSRF-Token": token}


def build_form_with_csrf(client, data: dict) -> dict:
    token = build_csrf_token()
    client.cookies.set(settings.CSRF_COOKIE_NAME, token)
    return {**data, "csrf_token": token}
