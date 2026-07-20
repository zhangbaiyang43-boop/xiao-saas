from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.response import RespVo


async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=RespVo(code=exc.status_code, msg=str(exc.detail), data=None).to_response(),
    )


async def validation_exception_handler(request: Request, exc):
    return JSONResponse(
        status_code=422,
        content=RespVo(code=422, msg="参数校验失败", data=None).to_response(),
    )
