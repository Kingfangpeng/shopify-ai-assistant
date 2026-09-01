"""CSRF/origin enforcement and browser security headers."""

from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth.security import valid_csrf
from app.config import config
from app.core.errors import error_response


class RequestSecurityMiddleware(BaseHTTPMiddleware):
    unsafe_methods = {"POST", "PUT", "PATCH", "DELETE"}

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.request_id = request.headers.get("X-Request-ID", str(uuid4()))[:100]
        path = request.url.path

        if path.startswith("/api/") and request.method in self.unsafe_methods:
            if not self._origin_allowed(request):
                return error_response("origin_rejected", "请求来源不受信任", 403, request.state.request_id)
            if path != "/api/auth/login":
                session_token = request.cookies.get(config.auth_cookie_name, "")
                supplied = request.headers.get("X-CSRF-Token", "")
                if not session_token:
                    return error_response("authentication_required", "请先登录", 401, request.state.request_id)
                if not valid_csrf(session_token, supplied):
                    return error_response("csrf_rejected", "安全令牌无效，请刷新后重试", 403, request.state.request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        return response

    @staticmethod
    def _origin_allowed(request: Request) -> bool:
        origin = request.headers.get("Origin")
        if not origin:
            return True
        parsed = urlsplit(origin)
        origin_host = parsed.hostname or ""
        request_host = (request.url.hostname or "").lower()
        if origin_host.lower() == request_host:
            return True
        return origin.rstrip("/") in {item.rstrip("/") for item in config.cors_origin_list}
