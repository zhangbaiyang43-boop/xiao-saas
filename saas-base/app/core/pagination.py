from app.config import settings


def normalize_pagination(skip: int = 0, limit: int = None) -> tuple[int, int]:
    safe_skip = max(int(skip or 0), 0)
    requested_limit = settings.PAGE_DEFAULT_LIMIT if limit is None else int(limit or settings.PAGE_DEFAULT_LIMIT)
    safe_limit = min(max(requested_limit, 1), settings.PAGE_MAX_LIMIT)
    return safe_skip, safe_limit


def build_page(items: list, total: int, skip: int, limit: int) -> dict:
    page_size = max(int(limit or settings.PAGE_DEFAULT_LIMIT), 1)
    current_page = int(skip / page_size) + 1
    return {
        "items": items,
        "total": int(total or 0),
        "skip": int(skip or 0),
        "limit": page_size,
        "page": current_page,
        "page_size": page_size,
    }
