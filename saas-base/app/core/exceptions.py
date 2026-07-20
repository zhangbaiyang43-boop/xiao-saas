from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.core.logger import logger
from app.core.response import RespVo


class BusinessException(Exception):
    def __init__(self, code: int = -1, message: str = "业务处理失败"):
        self.code = code
        self.message = message
        super().__init__(message)


async def business_exception_handler(request: Request, exc: BusinessException):
    logger.warning(
        f"Business exception: {exc.message}",
        extra={
            "request_id": getattr(request.state, "request_id", "unknown"),
            "code": exc.code,
        },
    )
    return JSONResponse(
        status_code=200,
        content=RespVo(code=exc.code, msg=exc.message, data=None).to_response(),
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning(
        f"HTTP exception: {exc.detail}",
        extra={
            "request_id": getattr(request.state, "request_id", "unknown"),
            "status_code": exc.status_code,
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=RespVo(code=exc.status_code, msg=str(exc.detail), data=None).to_response(),
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

    logger.warning(
        f"Validation error: {errors}",
        extra={"request_id": getattr(request.state, "request_id", "unknown")},
    )

    return JSONResponse(
        status_code=422,
        content=RespVo(code=422, msg="参数校验失败", data=errors).to_response(),
    )


async def general_exception_handler(request: Request, exc: Exception):
    logger.error(
        f"Unexpected error: {str(exc)}",
        extra={
            "request_id": getattr(request.state, "request_id", "unknown"),
            "exception": str(exc),
        },
    )
    return JSONResponse(
        status_code=500,
        content=RespVo(code=500, msg=str(exc) or "系统异常", data=None).to_response(),
    )
