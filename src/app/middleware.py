from collections import deque
from typing import Any

_MAX_LOGO_REQUEST_BODY_BYTES = 1 * 1024 * 1024 + 64 * 1024
_MAX_PDF_REQUEST_BODY_BYTES = 20 * 1024 * 1024 + 64 * 1024


def _upload_body_limit(scope: dict) -> int | None:
    path = scope.get("path")
    method = scope.get("method")
    if (
        method == "POST"
        and isinstance(path, str)
        and path.startswith("/api/organizations/")
        and path.endswith("/logo")
    ):
        return _MAX_LOGO_REQUEST_BODY_BYTES
    if method == "PUT" and isinstance(path, str) and "/documents/" in path:
        return _MAX_PDF_REQUEST_BODY_BYTES
    return None


class UploadBodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = _upload_body_limit(scope)
        if limit is None:
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        content_length = headers.get(b"content-length")
        if content_length is not None and int(content_length) > limit:
            await self._send_too_large(send)
            return
        messages: deque[dict[str, Any]] = deque()
        total_size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                messages.append(message)
                continue
            total_size += len(message.get("body", b""))
            if total_size > limit:
                await self._send_too_large(send)
                return
            messages.append(message)
            if not message.get("more_body", False):
                break

        async def replay_receive():
            if messages:
                return messages.popleft()
            return {"type": "http.disconnect"}

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _send_too_large(send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b'{"detail":"Request body is too large."}',
            }
        )
