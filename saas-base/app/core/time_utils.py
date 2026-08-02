from datetime import datetime, timezone


def to_utc_iso(dt: datetime | None) -> str | None:
    """序列化一个 naive UTC datetime 成带时区标记的 ISO 8601 字符串。

    这个项目里的 datetime 字段全部用 datetime.utcnow() 存的 naive UTC 时间，直接
    .isoformat() 出来的字符串不带时区后缀（如 "2026-08-16T15:59:00"）。前端
    new Date(...) 解析这种不带时区标记的字符串会当成本地时间处理，在 UTC+8 环境下
    会把实际的 UTC 时刻错读成晚 8 小时——这正是优惠券"还剩 X 小时过期"这类前端倒计时
    跟后端实际核销截止时间对不上的根因。补上 "+00:00" 后缀，让浏览器/小程序正确
    识别为 UTC 再按本地时区展示。
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
