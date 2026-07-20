import asyncio
import inspect
import unittest
from datetime import date

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.models.queue_ticket import QueueTicket
from app.services.queue_service import (
    KUAIMAI_QUEUE_TEMPLATE_ID,
    QueueCallBlocked,
    QueueService,
    build_queue_print_fields,
    build_queue_query_url,
    build_queue_template_render_data,
    build_queue_ticket_content,
    generate_queue_query_token,
    print_queue_ticket,
    print_queue_test_ticket,
    get_queue_type,
    serialize_queue_ticket_query,
    serialize_queue_ticket,
)


class QueueContractsTest(unittest.TestCase):
    def test_party_size_maps_to_queue_type(self):
        self.assertEqual(get_queue_type(1), "A")
        self.assertEqual(get_queue_type(2), "A")
        self.assertEqual(get_queue_type(3), "B")
        self.assertEqual(get_queue_type(4), "B")
        self.assertEqual(get_queue_type(5), "C")
        self.assertEqual(get_queue_type(8), "C")

    def test_queue_ticket_model_keeps_daily_unique_contract(self):
        constraints = {c.name for c in QueueTicket.__table__.constraints}
        indexes = {i.name for i in QueueTicket.__table__.indexes}
        self.assertIn("uq_queue_ticket_daily_type_sequence", constraints)
        self.assertIn("idx_queue_ticket_tenant_status_created", indexes)
        self.assertIn("idx_queue_ticket_tenant_date_type", indexes)

    def test_queue_ticket_model_requires_unique_query_token(self):
        indexes = {i.name: i for i in QueueTicket.__table__.indexes}
        self.assertFalse(QueueTicket.__table__.columns["query_token"].nullable)
        self.assertIn("idx_queue_ticket_query_token", indexes)
        self.assertTrue(indexes["idx_queue_ticket_query_token"].unique)

    def test_query_token_and_url_do_not_expose_tenant_or_sequence(self):
        token_a = generate_queue_query_token()
        token_b = generate_queue_query_token()
        self.assertNotEqual(token_a, token_b)
        self.assertGreaterEqual(len(token_a), 32)
        self.assertNotIn("001", token_a)
        self.assertEqual(build_queue_query_url(token_a, "https://saas.zhangbaiyang.com/"), f"https://saas.zhangbaiyang.com/queue/status?token={token_a}")
        self.assertNotIn("tenant_id", build_queue_query_url(token_a, "https://saas.zhangbaiyang.com"))

    def test_queue_template_id_is_pinned_for_queue_ticket(self):
        self.assertEqual(KUAIMAI_QUEUE_TEMPLATE_ID, "1634997391")

    def test_serialize_queue_ticket_exposes_public_contract(self):
        ticket = QueueTicket(id=1, tenant_id="1", queue_no="B001", queue_type="B", queue_date=date(2026, 7, 8), daily_sequence=1, party_size=3, phone="13800000000", note="window seat", status="waiting")
        payload = serialize_queue_ticket(ticket, ahead_count=2)
        self.assertEqual(payload["id"], "1")
        self.assertEqual(payload["queue_no"], "B001")
        self.assertEqual(payload["queue_type"], "B")
        self.assertEqual(payload["party_size"], 3)
        self.assertEqual(payload["phone_tail"], "0000")
        self.assertEqual(payload["status"], "waiting")
        self.assertEqual(payload["ahead_count"], 2)

    def test_serialize_queue_ticket_query_hides_sensitive_customer_fields(self):
        ticket = QueueTicket(id=1, tenant_id="tenant-a", queue_no="B001", queue_type="B", queue_date=date(2026, 7, 8), daily_sequence=1, party_size=3, phone="13800000000", note="window seat", status="waiting")
        payload = serialize_queue_ticket_query(ticket, merchant_name="A Store", ahead_count=2)
        self.assertEqual(payload["shop_name"], "A Store")
        self.assertEqual(payload["queue_number"], "B001")
        self.assertEqual(payload["queue_type_name"], "中桌")
        self.assertEqual(payload["party_size_text"], "3人")
        self.assertEqual(payload["waiting_text"], "前方等待2桌")
        self.assertIn("estimated_wait_text", payload)
        self.assertNotIn("phone", payload)
        self.assertNotIn("tenant_id", payload)

    def test_call_next_blocks_when_same_type_has_called_ticket(self):
        source = inspect.getsource(QueueService.call_next)
        self.assertIn('QueueTicket.status == "called"', source)
        self.assertIn('raise QueueCallBlocked(active_ticket)', source)
        active_ticket = QueueTicket(queue_no="A001", queue_type="A", status="called")
        error = QueueCallBlocked(active_ticket)
        self.assertIs(error.active_ticket, active_ticket)
        self.assertIn("current called", str(error))

    def test_queue_print_supports_kuaimai_provider(self):
        source = inspect.getsource(print_queue_ticket)
        self.assertIn('provider == "kuaimai"', source)
        self.assertIn('print_template_order', source)
        self.assertIn('KUAIMAI_QUEUE_TEMPLATE_ID', source)

    def test_queue_print_test_uses_sample_ticket_without_database_insert(self):
        source = inspect.getsource(print_queue_test_ticket)
        self.assertIn('queue_no="B000"', source)
        self.assertIn('return await print_queue_ticket', source)

    def test_build_queue_ticket_content_is_independent_from_order_ticket(self):
        ticket = QueueTicket(id=1, tenant_id="1", queue_no="C001", queue_type="C", queue_date=date(2026, 7, 8), daily_sequence=1, party_size=6, status="waiting")
        content = build_queue_ticket_content(ticket, merchant_name="Demo Restaurant", ahead_count=2)
        self.assertIn("Demo Restaurant", content)
        self.assertIn("C001", content)
        self.assertIn("6", content)
        self.assertIn("2", content)
        self.assertNotIn("order", content.lower())

    def test_build_queue_print_fields_include_personal_query_qrcode_mapping(self):
        ticket = QueueTicket(id=1, tenant_id="1", queue_no="C001", queue_type="C", queue_date=date(2026, 7, 8), daily_sequence=1, party_size=6, status="waiting")
        fields = build_queue_print_fields(ticket, merchant_name="Demo Restaurant", ahead_count=2, queue_url="https://saas.zhangbaiyang.com/queue/status?token=abc", queue_notice="扫码查看实时排队进度")
        self.assertEqual(fields["shop_name"], "Demo Restaurant")
        self.assertEqual(fields["queue_number"], "C001")
        self.assertEqual(fields["queue_type_name"], "大桌")
        self.assertEqual(fields["party_size_text"], "6人")
        self.assertEqual(fields["waiting_text"], "前方等待2桌")
        self.assertEqual(fields["waiting_count"], 2)
        self.assertEqual(fields["estimated_wait_minutes"], 15)
        self.assertEqual(fields["queue_url"], "https://saas.zhangbaiyang.com/queue/status?token=abc")
        self.assertEqual(fields["queue_notice"], "扫码查看实时排队进度")

    def test_build_queue_template_render_data_matches_template_fields(self):
        ticket = QueueTicket(id=1, tenant_id="1", queue_no="A018", queue_type="A", queue_date=date(2026, 7, 8), daily_sequence=18, party_size=2, status="waiting")
        render_data = build_queue_template_render_data(ticket, merchant_name="开心点餐测试店", ahead_count=6, queue_url="https://saas.zhangbaiyang.com/queue/status?token=abc", queue_notice="请留意现场叫号")
        self.assertEqual(render_data["shop_name"], "开心点餐测试店")
        self.assertEqual(render_data["queue_type_name"], "小桌")
        self.assertEqual(render_data["queue_number"], "A018")
        self.assertEqual(render_data["waiting_count"], 6)
        self.assertEqual(render_data["waiting_text"], "前方等待6桌")
        self.assertEqual(render_data["party_size"], 2)
        self.assertEqual(render_data["party_size_text"], "2人")
        self.assertEqual(render_data["estimated_wait_minutes"], 35)
        self.assertEqual(render_data["estimated_wait_text"], "约35分钟")
        self.assertEqual(render_data["queue_status"], "等待中")
        self.assertEqual(render_data["queue_url"], "https://saas.zhangbaiyang.com/queue/status?token=abc")
        self.assertEqual(render_data["queue_notice"], "请留意现场叫号")


if __name__ == "__main__":
    unittest.main()
