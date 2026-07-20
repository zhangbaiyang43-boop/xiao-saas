from typing import Optional, Generic, TypeVar
from pydantic import BaseModel

T = TypeVar('T')

class RespVo(BaseModel, Generic[T]):
    code: int = 200
    msg: str = "ok"
    data: Optional[T] = None
    
    class Config:
        arbitrary_types_allowed = True

    def to_response(self) -> dict:
        return self.model_dump()

def success_response(data: T = None, msg: str = "ok") -> RespVo[T]:
    return RespVo(code=200, msg=msg, data=data)

def error_response(code: int = -1, msg: str = "error", data: T = None) -> RespVo[T]:
    return RespVo(code=code, msg=msg, data=data)
