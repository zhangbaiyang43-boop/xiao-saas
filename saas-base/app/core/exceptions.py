from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.core.logger import logger
from app.core.request_context import RequestContext
from app.core.response import RespVo


def _request_id_of(request: Request) -> str:
    return getattr(request.state, "request_id", None) or RequestContext.get_request_id() or "unknown"


def _error_content(code: int, msg: str, request_id: str, data=None) -> dict:
    payload = RespVo(code=code, msg=msg, data=data).to_response()
    payload["request_id"] = request_id
    return payload


class BusinessException(Exception):
    def __init__(self, code: int = -1, message: str = "业务处理失败"):
        self.code = code
        self.message = message
        super().__init__(message)


async def business_exception_handler(request: Request, exc: BusinessException):
    request_id = _request_id_of(request)
    logger.warning(
        f"Business exception: {exc.message}",
        extra={
            "event": "BUSINESS_EXCEPTION",
            "request_id": request_id,
            "code": exc.code,
            "method": request.method,
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=200,
        content=_error_content(exc.code, exc.message, request_id),
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = _request_id_of(request)
    logger.warning(
        f"HTTP exception: {exc.detail}",
        extra={
            "event": "HTTP_EXCEPTION",
            "request_id": request_id,
            "status_code": exc.status_code,
            "method": request.method,
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_content(exc.status_code, str(exc.detail), request_id),
    )


async def validation_exception_handler(request: Request, exc: ValidationError):
    errors = []
    for error in exc.errors():
        errors.append(
            {
                "field": ".".join(str(item) for item in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
        )

    request_id = _request_id_of(request)
    logger.warning(
        f"Validation error: {errors}",
        extra={
            "event": "VALIDATION_ERROR",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
        },
    )

    return JSONResponse(
        status_code=422,
        content=_error_content(422, "参数校验失败", request_id, data=errors),
    )


async def general_exception_handler(request: Request, exc: Exception):
    request_id = _request_id_of(request)
    logger.exception(
        "UNHANDLED_EXCEPTION",
        extra={
            "event": "UNHANDLED_EXCEPTION",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "error_type": type(exc).__name__,
        },
    )
    return JSONResponse(
        status_code=500,
        content=_error_content(500, "系统异常，请稍后重试", request_id),
    )
