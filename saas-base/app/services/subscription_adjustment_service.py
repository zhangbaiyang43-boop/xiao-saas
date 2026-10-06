from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Plan, Subscription
from app.models.subscription_adjustment import SubscriptionAdjustment
from app.models.tenant import Tenant
from app.services.subscription_service import (
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_EXPIRED,
    STATUS_TRIAL,
    SubscriptionService,
    resolve_days_remaining,
)


ADJUSTMENT_GIFT = "GIFT"
ADJUSTMENT_COMPENSATION = "COMPENSATION"
ADJUSTMENT_TRIAL_EXTENSION = "TRIAL_EXTENSION"
ADJUSTMENT_CORRECTION = "CORRECTION"
ADJUSTMENT_INTERNAL_TEST = "INTERNAL_TEST"
ADJUSTMENT_OTHER = "OTHER"

OPERATION_ADD_DAYS = "ADD_DAYS"
OPERATION_SET_EXPIRY_DATE = "SET_EXPIRY_DATE"

TARGET_ENDS_AT = "ENDS_AT"
TARGET_TRIAL_ENDS_AT = "TRIAL_ENDS_AT"

_ADJUSTMENT_TYPES = {
    ADJUSTMENT_GIFT,
    ADJUSTMENT_COMPENSATION,
    ADJUSTMENT_TRIAL_EXTENSION,
    ADJUSTMENT_CORRECTION,
    ADJUSTMENT_INTERNAL_TEST,
    ADJUSTMENT_OTHER,
}
_NOTE_REQUIRED_TYPES = {
    ADJUSTMENT_COMPENSATION,
    ADJUSTMENT_CORRECTION,
    ADJUSTMENT_INTERNAL_TEST,
    ADJUSTMENT_OTHER,
}


class SubscriptionAdjustmentError(ValueError):
    def __init__(self, error_code: str, message: str, http_status: int = 422):
        self.error_code = error_code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


@dataclass(frozen=True)
class _NormalizedOperation:
    operation_type: str
    days: int | None
    expires_at: datetime | None
    adjustment_type: str
    reason: str
    note: str | None


@dataclass(frozen=True)
class _ResolvedTarget:
    subscription: Subscription
    plan: Plan
    target_field: str
    before_expiry: datetime
    before_status: str
    natural_expiry_recovery: bool


class SubscriptionAdjustmentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._subscriptions = SubscriptionService(db)

    @staticmethod
    def _error(error_code: str, message: str, http_status: int = 422) -> SubscriptionAdjustmentError:
        return SubscriptionAdjustmentError(error_code, message, http_status)

    @staticmethod
    def _normalize_text(value: str | None) -> str | None:
        normalized = (value or "").strip()
        return normalized or None

    @classmethod
    def _normalize_aware_datetime(cls, value: datetime | str | None, *, error_code: str) -> datetime:
        parsed: datetime
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            raw = value.strip()
            if not raw:
                raise cls._error(error_code, "到期时间不能为空")
            if not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})",
                raw,
            ):
                raise cls._error(error_code, "到期时间必须是带时区的 RFC3339 时间")
            try:
                parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
            except ValueError as exc:
                raise cls._error(error_code, "到期时间必须是带时区的 RFC3339 时间") from exc
        else:
            raise cls._error(error_code, "到期时间必须是带时区的 RFC3339 时间")
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise cls._error(error_code, "到期时间必须包含 Z 或明确时区偏移")
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)

    @classmethod
    def _normalize_operation(
        cls,
        *,
        operation_type: str,
        days: Any,
        expires_at: datetime | str | None,
        adjustment_type: str,
        reason: str,
        note: str | None,
    ) -> _NormalizedOperation:
        operation = (operation_type or "").strip().upper()
        adjustment = (adjustment_type or "").strip().upper()
        normalized_reason = cls._normalize_text(reason)
        normalized_note = cls._normalize_text(note)

        if adjustment not in _ADJUSTMENT_TYPES:
            raise cls._error("INVALID_ADJUSTMENT_TYPE_FOR_STATE", "不支持的调整类型")
        if normalized_reason is None or len(normalized_reason) > 255:
            raise cls._error("INVALID_ADJUSTMENT_TYPE_FOR_STATE", "调整原因必填且不能超过 255 个字符")
        if adjustment in _NOTE_REQUIRED_TYPES and normalized_note is None:
            raise cls._error("NOTE_REQUIRED", "该调整类型必须填写备注")

        if operation == OPERATION_ADD_DAYS:
            if type(days) is not int or days <= 0:
                raise cls._error("INVALID_DAYS", "增加天数必须是 1 至 365 的整数")
            if days > 365:
                raise cls._error("ADD_DAYS_EXCEEDS_LIMIT", "单次增加不能超过 365 天，请改用修改到期日")
            if expires_at is not None:
                raise cls._error("INVALID_DAYS", "增加时长不能同时提交指定到期日")
            normalized_expiry = None
        elif operation == OPERATION_SET_EXPIRY_DATE:
            if days is not None:
                raise cls._error("INVALID_DAYS", "修改到期日不能同时提交增加天数")
            normalized_expiry = cls._normalize_aware_datetime(
                expires_at,
                error_code="INVALID_EXPIRY_TIMESTAMP",
            )
        else:
            raise cls._error("INVALID_OPERATION", "不支持的服务期调整方式")

        return _NormalizedOperation(
            operation_type=operation,
            days=days if operation == OPERATION_ADD_DAYS else None,
            expires_at=normalized_expiry,
            adjustment_type=adjustment,
            reason=normalized_reason,
            note=normalized_note,
        )

    async def _load_tenant(self, tenant_id: str, *, lock: bool) -> Tenant:
        query = select(Tenant).where(Tenant.tenant_id == tenant_id)
        if lock:
            query = query.with_for_update()
        result = await self.db.execute(query)
        tenant = result.scalar_one_or_none()
        if tenant is None:
            raise self._error("TENANT_NOT_FOUND", "商户不存在", 404)
        return tenant

    async def _load_subscriptions(self, tenant_id: str, *, lock: bool) -> list[Subscription]:
        query = (
            select(Subscription)
            .where(Subscription.tenant_id == tenant_id)
            .order_by(Subscription.created_at.desc(), Subscription.id.desc())
        )
        if lock:
            query = query.with_for_update()
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def _resolve_target(
        self,
        tenant_id: str,
        *,
        now: datetime,
        lock: bool,
        adjustment_type: str | None = None,
    ) -> _ResolvedTarget:
        rows = await self._load_subscriptions(tenant_id, lock=lock)
        if not rows:
            raise self._error("NO_ADJUSTABLE_SUBSCRIPTION", "当前无可调整的有效服务期", 409)

        latest = rows[0]
        effective = next((row for row in rows if self._subscriptions.is_active(row, now=now)), None)
        if effective is not None and effective.id != latest.id:
            raise self._error("STALE_SUBSCRIPTION", "订阅记录存在覆盖关系，请刷新后重新确认", 409)

        if effective is None:
            if latest.status == STATUS_EXPIRED:
                raise self._error("SUBSCRIPTION_EXPIRED", "显式过期的订阅不能通过普通调整恢复", 409)
            if latest.status == STATUS_CANCELLED:
                raise self._error("SUBSCRIPTION_CANCELLED", "已取消的订阅不能调整服务期", 409)
            if latest.status not in (STATUS_ACTIVE, STATUS_TRIAL):
                raise self._error("NO_ADJUSTABLE_SUBSCRIPTION", "当前无可调整的有效服务期", 409)
            natural_recovery = True
        else:
            latest = effective
            natural_recovery = False

        if latest.status == STATUS_ACTIVE:
            target_field = TARGET_ENDS_AT
            before_expiry = latest.ends_at
        elif latest.status == STATUS_TRIAL:
            target_field = TARGET_TRIAL_ENDS_AT
            before_expiry = latest.trial_ends_at
        elif latest.status == STATUS_EXPIRED:
            raise self._error("SUBSCRIPTION_EXPIRED", "显式过期的订阅不能通过普通调整恢复", 409)
        elif latest.status == STATUS_CANCELLED:
            raise self._error("SUBSCRIPTION_CANCELLED", "已取消的订阅不能调整服务期", 409)
        else:
            raise self._error("NO_ADJUSTABLE_SUBSCRIPTION", "当前无可调整的有效服务期", 409)

        if before_expiry is None:
            raise self._error("INFINITE_EXPIRY", "无限期服务不能使用普通服务期调整", 409)
        if natural_recovery and before_expiry > now:
            raise self._error("CONCURRENT_MODIFICATION", "订阅状态已变化，请刷新后重试", 409)
        if adjustment_type == ADJUSTMENT_TRIAL_EXTENSION and latest.status != STATUS_TRIAL:
            raise self._error("INVALID_ADJUSTMENT_TYPE_FOR_STATE", "试用延长只能用于试用订阅")

        plan_result = await self.db.execute(select(Plan).where(Plan.id == latest.plan_id))
        plan = plan_result.scalar_one_or_none()
        if plan is None:
            raise self._error("CONCURRENT_MODIFICATION", "订阅套餐数据不完整，请稍后重试", 409)
        if plan.code == "FREE":
            raise self._error("NO_ADJUSTABLE_SUBSCRIPTION", "免费版没有可调整的有效服务期", 409)

        return _ResolvedTarget(
            subscription=latest,
            plan=plan,
            target_field=target_field,
            before_expiry=before_expiry,
            before_status=STATUS_EXPIRED if natural_recovery else latest.status,
            natural_expiry_recovery=natural_recovery,
        )

    @classmethod
    def _calculate_after(
        cls,
        target: _ResolvedTarget,
        operation: _NormalizedOperation,
        *,
        now: datetime,
    ) -> tuple[datetime, datetime]:
        base_expiry = max(now, target.before_expiry)
        if operation.operation_type == OPERATION_ADD_DAYS:
            return base_expiry, base_expiry + timedelta(days=operation.days)
        assert operation.expires_at is not None
        if operation.expires_at <= base_expiry:
            raise cls._error("EXPIRY_SHORTEN_NOT_ALLOWED", "新到期时间必须严格晚于当前计算基线")
        return base_expiry, operation.expires_at

    @staticmethod
    def _iso_utc(value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")

    def _result_from_values(
        self,
        *,
        tenant_id: str,
        target: _ResolvedTarget,
        operation: _NormalizedOperation,
        base_expiry: datetime,
        after_expiry: datetime,
        previewed_at: datetime | None = None,
        adjustment: SubscriptionAdjustment | None = None,
        idempotent_replay: bool = False,
        result_status: str | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "tenant_id": tenant_id,
            "subscription_id": str(target.subscription.id),
            "subscription_status": result_status or target.before_status,
            "target_field": target.target_field,
            "before_expiry": self._iso_utc(target.before_expiry),
            "calculation_base_expiry": self._iso_utc(base_expiry),
            "after_expiry": self._iso_utc(after_expiry),
            "delta_days": operation.days,
            "effective_plan": {"plan_code": target.plan.code, "plan_name": target.plan.name},
            "adjustment_type": operation.adjustment_type,
            "operation_type": operation.operation_type,
            "natural_expiry_recovery": target.natural_expiry_recovery,
        }
        if previewed_at is not None:
            data["previewed_at"] = self._iso_utc(previewed_at)
        if adjustment is not None:
            data.update(
                {
                    "adjustment_id": str(adjustment.id),
                    "created_at": self._iso_utc(adjustment.created_at),
                    "idempotent_replay": idempotent_replay,
                }
            )
        return data

    async def preview(
        self,
        tenant_id: str,
        *,
        operation_type: str,
        days: Any = None,
        expires_at: datetime | str | None = None,
        adjustment_type: str,
        reason: str,
        note: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        reference_now = now or datetime.utcnow()
        operation = self._normalize_operation(
            operation_type=operation_type,
            days=days,
            expires_at=expires_at,
            adjustment_type=adjustment_type,
            reason=reason,
            note=note,
        )
        await self._load_tenant(tenant_id, lock=False)
        target = await self._resolve_target(
            tenant_id,
            now=reference_now,
            lock=False,
            adjustment_type=operation.adjustment_type,
        )
        base_expiry, after_expiry = self._calculate_after(target, operation, now=reference_now)
        return self._result_from_values(
            tenant_id=tenant_id,
            target=target,
            operation=operation,
            base_expiry=base_expiry,
            after_expiry=after_expiry,
            previewed_at=reference_now,
        )

    @classmethod
    def _fingerprint(
        cls,
        *,
        tenant_id: str,
        operation: _NormalizedOperation,
        expected_subscription_id: int,
        expected_before_expiry: datetime,
    ) -> str:
        payload = {
            "tenant_id": tenant_id,
            "operation_type": operation.operation_type,
            "days": operation.days,
            "expires_at": cls._iso_utc(operation.expires_at),
            "adjustment_type": operation.adjustment_type,
            "reason": operation.reason,
            "note": operation.note,
            "expected_subscription_id": str(expected_subscription_id),
            "expected_before_expiry": cls._iso_utc(expected_before_expiry),
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def _find_adjustment(
        self,
        tenant_id: str,
        idempotency_key: str,
        *,
        lock: bool = False,
    ) -> SubscriptionAdjustment | None:
        query = select(SubscriptionAdjustment).where(
                SubscriptionAdjustment.tenant_id == tenant_id,
                SubscriptionAdjustment.idempotency_key == idempotency_key,
            )
        if lock:
            query = query.with_for_update()
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _replay_result(
        self,
        adjustment: SubscriptionAdjustment,
        *,
        fingerprint: str,
    ) -> dict[str, Any]:
        if adjustment.request_fingerprint != fingerprint:
            raise self._error("DUPLICATE_REQUEST", "该幂等键已用于不同的调整请求", 409)
        plan_result = await self.db.execute(select(Plan).where(Plan.code == adjustment.plan_code))
        plan = plan_result.scalar_one_or_none()
        plan_name = plan.name if plan is not None else adjustment.plan_code
        return {
            "tenant_id": adjustment.tenant_id,
            "subscription_id": str(adjustment.subscription_id),
            "subscription_status": adjustment.after_status,
            "target_field": adjustment.target_field,
            "before_expiry": self._iso_utc(adjustment.before_expiry),
            "calculation_base_expiry": self._iso_utc(adjustment.calculation_base_expiry),
            "after_expiry": self._iso_utc(adjustment.after_expiry),
            "delta_days": adjustment.delta_days,
            "effective_plan": {"plan_code": adjustment.plan_code, "plan_name": plan_name},
            "adjustment_type": adjustment.adjustment_type,
            "operation_type": adjustment.operation_type,
            "natural_expiry_recovery": adjustment.natural_expiry_recovery,
            "adjustment_id": str(adjustment.id),
            "created_at": self._iso_utc(adjustment.created_at),
            "idempotent_replay": True,
        }

    async def commit(
        self,
        tenant_id: str,
        *,
        operation_type: str,
        days: Any = None,
        expires_at: datetime | str | None = None,
        adjustment_type: str,
        reason: str,
        note: str | None = None,
        expected_subscription_id: int,
        expected_before_expiry: datetime | str,
        idempotency_key: str,
        operator_type: str,
        operator_id: str | None,
        operator_label: str,
        operator_ip: str,
        request_id: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        operation = self._normalize_operation(
            operation_type=operation_type,
            days=days,
            expires_at=expires_at,
            adjustment_type=adjustment_type,
            reason=reason,
            note=note,
        )
        normalized_before = self._normalize_aware_datetime(
            expected_before_expiry,
            error_code="INVALID_EXPIRY_TIMESTAMP",
        )
        try:
            normalized_key = str(UUID(str(idempotency_key)))
        except (ValueError, TypeError, AttributeError) as exc:
            raise self._error("INVALID_IDEMPOTENCY_KEY", "幂等键必须是 UUID") from exc
        fingerprint = self._fingerprint(
            tenant_id=tenant_id,
            operation=operation,
            expected_subscription_id=int(expected_subscription_id),
            expected_before_expiry=normalized_before,
        )

        try:
            await self._load_tenant(tenant_id, lock=True)
            existing = await self._find_adjustment(tenant_id, normalized_key, lock=True)
            if existing is not None:
                return await self._replay_result(existing, fingerprint=fingerprint)

            # Take the authoritative clock reading only after tenant-level
            # serialization. A natural-expiry recovery must grant the full
            # requested future period even when this request waited on a lock.
            reference_now = now or datetime.utcnow()
            target = await self._resolve_target(
                tenant_id,
                now=reference_now,
                lock=True,
                adjustment_type=operation.adjustment_type,
            )
            if int(target.subscription.id) != int(expected_subscription_id):
                raise self._error("STALE_SUBSCRIPTION", "订阅记录已变化，请刷新后重新确认", 409)
            if target.before_expiry != normalized_before:
                raise self._error("STALE_SUBSCRIPTION", "到期时间已变化，请刷新后重新确认", 409)

            base_expiry, after_expiry = self._calculate_after(target, operation, now=reference_now)
            adjustment = SubscriptionAdjustment(
                tenant_id=tenant_id,
                subscription_id=target.subscription.id,
                plan_code=target.plan.code,
                target_field=target.target_field,
                adjustment_type=operation.adjustment_type,
                operation_type=operation.operation_type,
                delta_days=operation.days,
                before_expiry=target.before_expiry,
                calculation_base_expiry=base_expiry,
                after_expiry=after_expiry,
                before_status=target.before_status,
                after_status=target.subscription.status,
                stored_subscription_status=target.subscription.status,
                natural_expiry_recovery=target.natural_expiry_recovery,
                reason=operation.reason,
                note=operation.note,
                operator_type=operator_type,
                operator_id=operator_id,
                operator_label=operator_label,
                operator_ip=operator_ip,
                request_id=request_id,
                idempotency_key=normalized_key,
                request_fingerprint=fingerprint,
            )
            self.db.add(adjustment)
            if target.target_field == TARGET_ENDS_AT:
                target.subscription.ends_at = after_expiry
            else:
                target.subscription.trial_ends_at = after_expiry
            await self.db.flush()
            await self.db.commit()
            return self._result_from_values(
                tenant_id=tenant_id,
                target=target,
                operation=operation,
                base_expiry=base_expiry,
                after_expiry=after_expiry,
                adjustment=adjustment,
                result_status=target.subscription.status,
            )
        except SubscriptionAdjustmentError:
            await self.db.rollback()
            raise
        except IntegrityError as exc:
            await self.db.rollback()
            raced = await self._find_adjustment(tenant_id, normalized_key)
            if raced is not None:
                return await self._replay_result(raced, fingerprint=fingerprint)
            raise self._error("CONCURRENT_MODIFICATION", "并发调整冲突，请刷新后重试", 409) from exc
        except Exception:
            await self.db.rollback()
            raise

    async def list_history(self, tenant_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        if type(limit) is not int or not 1 <= limit <= 20:
            raise self._error("INVALID_HISTORY_LIMIT", "历史记录条数必须在 1 至 20 之间")
        await self._load_tenant(tenant_id, lock=False)
        result = await self.db.execute(
            select(SubscriptionAdjustment)
            .where(SubscriptionAdjustment.tenant_id == tenant_id)
            .order_by(SubscriptionAdjustment.created_at.desc(), SubscriptionAdjustment.id.desc())
            .limit(limit)
        )
        rows = list(result.scalars().all())
        plan_codes = {row.plan_code for row in rows}
        plan_names: dict[str, str] = {}
        if plan_codes:
            plan_result = await self.db.execute(select(Plan).where(Plan.code.in_(plan_codes)))
            plan_names = {plan.code: plan.name for plan in plan_result.scalars().all()}
        return [
            {
                "adjustment_id": str(row.id),
                "subscription_id": str(row.subscription_id),
                "plan": {
                    "plan_code": row.plan_code,
                    "plan_name": plan_names.get(row.plan_code, row.plan_code),
                },
                "adjustment_type": row.adjustment_type,
                "operation_type": row.operation_type,
                "delta_days": row.delta_days,
                "before_expiry": self._iso_utc(row.before_expiry),
                "calculation_base_expiry": self._iso_utc(row.calculation_base_expiry),
                "after_expiry": self._iso_utc(row.after_expiry),
                "natural_expiry_recovery": row.natural_expiry_recovery,
                "reason": row.reason,
                "note": row.note,
                "operator_label": row.operator_label,
                "operator_ip": row.operator_ip,
                "created_at": self._iso_utc(row.created_at),
            }
            for row in rows
        ]

    async def get_adjustment_context(self, tenant_id: str, *, now: datetime | None = None) -> dict[str, Any]:
        reference_now = now or datetime.utcnow()
        try:
            await self._load_tenant(tenant_id, lock=False)
            target = await self._resolve_target(tenant_id, now=reference_now, lock=False)
        except SubscriptionAdjustmentError as exc:
            return {"adjustable": False, "action": None, "error_code": exc.error_code}
        subscription = target.subscription
        started_at = subscription.started_at if subscription.status == STATUS_ACTIVE else subscription.trial_started_at
        return {
            "adjustable": True,
            "action": "RECOVER" if target.natural_expiry_recovery else "ADJUST",
            "error_code": None,
            "subscription_id": str(subscription.id),
            "stored_status": subscription.status,
            "subscription_status": target.before_status,
            "plan_code": target.plan.code,
            "plan_name": target.plan.name,
            "started_at": self._iso_utc(started_at),
            "expires_at": self._iso_utc(target.before_expiry),
            "days_remaining": resolve_days_remaining(target.before_expiry, now=reference_now),
            "target_field": target.target_field,
            "natural_expiry_recovery": target.natural_expiry_recovery,
        }
