"""订阅消息组装与发送守卫。"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.subscribe_message_service import (
    build_order_success_data,
    build_pickup_reminder_data,
    build_queue_reminder_data,
    is_real_wechat_openid,
    resolve_pickup_no,
    send_order_success_subscribe,
    send_pickup_reminder_subscribe,
    send_queue_reminder_subscribe,
)


class SubscribeMessageServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_is_real_wechat_openid_filters_synthetic(self):
        self.assertTrue(is_real_wechat_openid("oXXXXXXXX"))
        self.assertFalse(is_real_wechat_openid(""))
        self.assertFalse(is_real_wechat_openid(None))
        self.assertFalse(is_real_wechat_openid("phone:13800000000"))
        self.assertFalse(is_real_wechat_openid("manual-abc"))

    def test_build_order_success_data_field_keys(self):
        data = build_order_success_data(
            pickup_no="07",
            amount=28.5,
            shop_name="开心小馆",
            status_text="已支付",
            payment_time="2026-08-07T11:30:00+08:00",
        )
        self.assertEqual(set(data.keys()), {"character_string1", "amount2", "thing3", "phrase4", "time5"})
        self.assertEqual(data["character_string1"]["value"], "07")
        self.assertEqual(data["amount2"]["value"], "28.50")
        self.assertEqual(data["thing3"]["value"], "开心小馆")
        self.assertEqual(data["phrase4"]["value"], "已支付")
        self.assertIn("2026-08-07", data["time5"]["value"])

    def test_build_pickup_reminder_data_field_keys(self):
        data = build_pickup_reminder_data(
            pickup_no="07",
            shop_name="开心小馆",
            product_name="宫保鸡丁等",
        )
        self.assertEqual(set(data.keys()), {"character_string1", "thing2", "phrase3", "thing4", "thing5"})
        self.assertEqual(data["thing5"]["value"], "请到前台取餐")
        self.assertEqual(data["thing4"]["value"], "宫保鸡丁等")

    def test_resolve_pickup_no_does_not_fall_back_to_table(self):
        order = SimpleNamespace(pickup_no=None, table_no="A01")
        self.assertEqual(resolve_pickup_no(order), "—")

    async def test_send_order_success_skips_without_openid(self):
        order = SimpleNamespace(id=1, customer_id=None, total=10, pickup_no="1", payment_time=None, tenant_id="t1")
        db = AsyncMock()
        with patch("app.services.subscribe_message_service.settings") as settings:
            settings.WECHAT_ORDER_SUCCESS_TEMPLATE_ID = "tmpl-order"
            sent = await send_order_success_subscribe(db, order)
        self.assertFalse(sent)

    async def test_send_order_success_calls_wechat(self):
        order = SimpleNamespace(
            id=9,
            customer_id=3,
            total=12,
            pickup_no="08",
            payment_time="2026-08-07T12:00:00+08:00",
            tenant_id="t1",
            table_no="A1",
        )
        customer = SimpleNamespace(openid="oRealOpenId")
        tenant = SimpleNamespace(name="测试店")
        db = AsyncMock()
        db.get = AsyncMock(return_value=customer)
        db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: tenant))

        wechat = AsyncMock()
        wechat.send_subscribe_message = AsyncMock(return_value=True)

        with patch("app.services.subscribe_message_service.settings") as settings, patch(
            "app.services.wechat_service.WechatService", return_value=wechat
        ):
            settings.WECHAT_ORDER_SUCCESS_TEMPLATE_ID = "tmpl-order"
            sent = await send_order_success_subscribe(db, order)

        self.assertTrue(sent)
        wechat.send_subscribe_message.assert_awaited_once()
        kwargs = wechat.send_subscribe_message.await_args.kwargs
        self.assertEqual(kwargs["openid"], "oRealOpenId")
        self.assertEqual(kwargs["template_id"], "tmpl-order")
        self.assertIn("character_string1", kwargs["data"])

    async def test_send_pickup_skips_synthetic_openid(self):
        order = SimpleNamespace(id=2, customer_id=4, total=10, pickup_no="1", tenant_id="t1", table_no="A")
        customer = SimpleNamespace(openid="phone:13800000000")
        db = AsyncMock()
        db.get = AsyncMock(return_value=customer)

        with patch("app.services.subscribe_message_service.settings") as settings:
            settings.WECHAT_PICKUP_REMINDER_TEMPLATE_ID = "tmpl-pickup"
            sent = await send_pickup_reminder_subscribe(db, order)
        self.assertFalse(sent)

    def test_build_queue_reminder_data_field_keys(self):
        data = build_queue_reminder_data(
            queue_no="B003",
            status_text="已叫号",
            current_called="B003",
            shop_name="开心小馆",
        )
        self.assertEqual(
            set(data.keys()),
            {"character_string1", "phrase2", "character_string3", "thing4", "thing5"},
        )
        self.assertEqual(data["character_string1"]["value"], "B003")
        self.assertEqual(data["phrase2"]["value"], "已叫号")
        self.assertEqual(data["thing5"]["value"], "请尽快到前台就坐")

    async def test_send_queue_reminder_skips_without_openid(self):
        ticket = SimpleNamespace(id=3, queue_no="A001", openid=None, tenant_id="t1")
        db = AsyncMock()
        with patch("app.services.subscribe_message_service.settings") as settings:
            settings.WECHAT_QUEUE_REMINDER_TEMPLATE_ID = "tmpl-queue"
            sent = await send_queue_reminder_subscribe(db, ticket)
        self.assertFalse(sent)

    async def test_send_queue_reminder_calls_wechat(self):
        ticket = SimpleNamespace(id=4, queue_no="B002", openid="oRealOpenId", tenant_id="t1")
        tenant = SimpleNamespace(name="测试店")
        db = AsyncMock()
        db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: tenant))
        wechat = AsyncMock()
        wechat.send_subscribe_message = AsyncMock(return_value=True)

        with patch("app.services.subscribe_message_service.settings") as settings, patch(
            "app.services.wechat_service.WechatService", return_value=wechat
        ):
            settings.WECHAT_QUEUE_REMINDER_TEMPLATE_ID = "tmpl-queue"
            sent = await send_queue_reminder_subscribe(db, ticket)

        self.assertTrue(sent)
        kwargs = wechat.send_subscribe_message.await_args.kwargs
        self.assertEqual(kwargs["template_id"], "tmpl-queue")
        self.assertEqual(kwargs["data"]["character_string1"]["value"], "B002")


if __name__ == "__main__":
    unittest.main()
