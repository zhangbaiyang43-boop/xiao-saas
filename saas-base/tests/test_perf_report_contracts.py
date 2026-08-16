
import unittest

from app.api.v1.perf import report_perf_samples


class FakeRequest:
    def __init__(self, body):
        self.body = body

    async def json(self):
        return self.body


class FakeDb:
    def __init__(self):
        self.rows = []
        self.commits = 0

    def add_all(self, rows):
        self.rows.extend(rows)

    async def commit(self):
        self.commits += 1


class PerfReportContractsTest(unittest.IsolatedAsyncioTestCase):
    async def test_new_timeline_and_legacy_metrics_are_accepted_unknown_is_rejected(self):
        db = FakeDb()
        response = await report_perf_samples(FakeRequest({
            "tenant_id": "tenant-1",
            "client_id": "client-1",
            "samples": [
                {"metric": "menu_onload_to_interactive", "ms": 321, "meta": '{"validity":"valid"}'},
                {"metric": "menu_api", "ms": 123},
                {"metric": "not_allowed", "ms": 1},
            ],
        }), db)

        self.assertEqual(response.code, 200)
        self.assertEqual(response.msg, "ok")
        self.assertEqual(response.data, {"accepted": 2})
        self.assertEqual([row.metric for row in db.rows], ["menu_onload_to_interactive", "menu_api"])
        self.assertEqual(db.commits, 1)

    async def test_existing_invalid_body_response_contract_is_unchanged(self):
        db = FakeDb()
        response = await report_perf_samples(FakeRequest({"samples": "invalid"}), db)

        self.assertEqual(response.model_dump(), {
            "code": 200,
            "msg": "ok",
            "data": {"accepted": 0},
        })
        self.assertEqual(db.rows, [])
        self.assertEqual(db.commits, 0)


if __name__ == "__main__":
    unittest.main()
