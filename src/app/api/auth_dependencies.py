from fastapi import HTTPException, Request, status

from src.app.services.auth import AuthenticatedUser


def get_request_auth_user(request: Request) -> AuthenticatedUser | None:
    user = getattr(request.state, "current_user", None)
    return user if isinstance(user, AuthenticatedUser) else None


def require_authenticated_user(request: Request) -> AuthenticatedUser:
    user = get_request_auth_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация.",
        )
    return user


def require_editor_user(request: Request) -> AuthenticatedUser:
    user = require_authenticated_user(request)
    if not user.can_edit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для изменения данных.",
        )
    return user
