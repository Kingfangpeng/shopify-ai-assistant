"""Application-safe error types and response helpers."""

from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def error_response(code: str, message: str, status_code: int, request_id: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "request_id": request_id or str(uuid4())}},
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return error_response(exc.code, exc.message, exc.status_code, getattr(request.state, "request_id", None))


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    messages = {401: "请先登录", 403: "没有权限执行此操作", 404: "请求的资源不存在"}
    return error_response(
        f"http_{exc.status_code}",
        messages.get(exc.status_code, "请求未能完成"),
        exc.status_code,
        getattr(request.state, "request_id", None),
    )


async def validation_error_handler(request: Request, _exc: RequestValidationError) -> JSONResponse:
    return error_response("validation_error", "请求参数格式不正确", 422, getattr(request.state, "request_id", None))


async def unexpected_error_handler(request: Request, _exc: Exception) -> JSONResponse:
    logger.exception("未处理的服务端异常，request_id={}", getattr(request.state, "request_id", "unknown"))
    return error_response("internal_error", "服务暂时不可用", 500, getattr(request.state, "request_id", None))
