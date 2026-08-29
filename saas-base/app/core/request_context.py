from contextvars import ContextVar, Token

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


class RequestContext:
    """Per-request correlation id. Independent of TenantContext — do not merge."""

    @classmethod
    def set_request_id(cls, request_id: str | None) -> Token:
        return _request_id.set(request_id)

    @classmethod
    def get_request_id(cls) -> str | None:
        return _request_id.get()

    @classmethod
    def reset(cls, token: Token) -> None:
        _request_id.reset(token)
