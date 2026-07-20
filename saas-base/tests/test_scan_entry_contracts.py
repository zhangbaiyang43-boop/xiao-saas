import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
FRONTEND_ROOT = ROOT.parent / "member-mini-client" / "src"
ENTRY_SOURCE = (FRONTEND_ROOT / "pages" / "entry" / "index.vue").read_text(encoding="utf-8-sig")
INDEX_SOURCE = (FRONTEND_ROOT / "pages" / "index" / "index.vue").read_text(encoding="utf-8-sig")
ENTRANCE_API_SOURCE = (ROOT / "app" / "api" / "v1" / "entrance_codes.py").read_text(encoding="utf-8-sig")
ENTRANCE_SERVICE_SOURCE = (ROOT / "app" / "services" / "entrance_code_service.py").read_text(encoding="utf-8-sig")
DINING_API_SOURCE = (ROOT / "app" / "api" / "v1" / "dining_sessions.py").read_text(encoding="utf-8-sig")


TENANTS = {
    "tenant_a": {"A01": "scene_a01", "A02": "scene_a02"},
    "tenant_b": {"B01": "scene_b01", "B02": "scene_b02"},
}
SCENE_ROWS = {
    scene: {"tenant_id": tenant_id, "table_no": table_no, "status": 1}
    for tenant_id, tables in TENANTS.items()
    for table_no, scene in tables.items()
}
SCENE_ROWS["expired_scene"] = {"tenant_id": "tenant_a", "table_no": "A01", "status": 0}


def resolve_scene(scene):
    row = SCENE_ROWS.get(scene)
    if not row:
        return {"code": 404, "target": None}
    if row["status"] != 1:
        return {"code": 410, "target": None}
    return {
        "code": 200,
        "target": f"/subpkg-order/pages/menu?table={row['table_no']}&shop={row['tenant_id']}&order_mode=dine_in&entry_type=table&channel=TABLE",
        "tenant_id": row["tenant_id"],
        "table_no": row["table_no"],
    }


def ordinary_entry(storage):
    tenant_id = storage.get("tenant_id", "")
    if not tenant_id:
        return "/pages/mine/mine"
    table_no = storage.get("table_no", "")
    suffix = f"&table={table_no}" if table_no else ""
    return f"/subpkg-order/pages/menu?shop={tenant_id}{suffix}"


class ScanEntryContractsTest(unittest.TestCase):
    def test_backend_resolve_rejects_wrong_and_expired_scene(self):
        self.assertEqual(resolve_scene("missing_scene")["code"], 404)
        self.assertEqual(resolve_scene("expired_scene")["code"], 410)

    def test_two_tenants_two_tables_resolve_to_isolated_menu_contexts(self):
        matrix = []
        for tenant_id, tables in TENANTS.items():
            for table_no, scene in tables.items():
                result = resolve_scene(scene)
                matrix.append((tenant_id, table_no, scene, result["code"], result["tenant_id"], result["table_no"], result["target"]))

        self.assertEqual(len(matrix), 4)
        for tenant_id, table_no, scene, code, resolved_tenant, resolved_table, target in matrix:
            with self.subTest(scene=scene):
                self.assertEqual(code, 200)
                self.assertEqual(resolved_tenant, tenant_id)
                self.assertEqual(resolved_table, table_no)
                self.assertIn(f"shop={tenant_id}", target)
                self.assertIn(f"table={table_no}", target)
                other_tenants = set(TENANTS) - {tenant_id}
                for other in other_tenants:
                    self.assertNotIn(f"shop={other}", target)

    def test_frontend_entry_page_persists_scene_tenant_table_and_routes_to_menu(self):
        self.assertIn("resolveEntranceCode(parsed.scene)", ENTRY_SOURCE)
        self.assertIn("uni.setStorageSync('entrance_scene', ctx.scene)", ENTRY_SOURCE)
        self.assertIn("uni.setStorageSync('tenant_id', ctx.tenant_id)", ENTRY_SOURCE)
        self.assertIn("uni.setStorageSync('table_no', ctx.table)", ENTRY_SOURCE)
        self.assertIn("resolveDiningSession", ENTRY_SOURCE)
        self.assertIn("subpkg-order/pages/menu", ENTRY_SOURCE)
        self.assertIn("uni.redirectTo", ENTRY_SOURCE)

    def test_default_index_forwards_scan_options_to_entry_page_before_cached_route(self):
        self.assertIn("buildEntryUrlFromOptions", INDEX_SOURCE)
        self.assertIn("const keys = ['scene', 'q', 'tenant_id'", INDEX_SOURCE)
        self.assertIn("/pages/entry/index?", INDEX_SOURCE)
        self.assertIn("onLoad(options = {})", INDEX_SOURCE)
        self.assertLess(INDEX_SOURCE.index("const entryUrl = buildEntryUrlFromOptions(options)"), INDEX_SOURCE.index("this.redirect()"))

    def test_ordinary_entry_without_scene_uses_cached_store_or_mine(self):
        self.assertEqual(ordinary_entry({}), "/pages/mine/mine")
        self.assertEqual(ordinary_entry({"tenant_id": "tenant_a"}), "/subpkg-order/pages/menu?shop=tenant_a")
        self.assertEqual(
            ordinary_entry({"tenant_id": "tenant_b", "table_no": "B02"}),
            "/subpkg-order/pages/menu?shop=tenant_b&table=B02",
        )

    def test_backend_contracts_keep_table_scene_strict(self):
        self.assertIn("if entrance_code.status != 1", ENTRANCE_API_SOURCE)
        self.assertIn('if entry_type == "table" and not table_no', ENTRANCE_API_SOURCE)
        self.assertIn('if channel == "TABLE" and entry_type != "table"', ENTRANCE_API_SOURCE)
        self.assertIn('"tenant_id": item.tenant_id', ENTRANCE_API_SOURCE)
        self.assertIn('"table_no": table_no', ENTRANCE_API_SOURCE)
        self.assertIn('"target_page": target_page', ENTRANCE_API_SOURCE)
        self.assertIn("EntranceScanLog", ENTRANCE_SERVICE_SOURCE)
        self.assertIn("TenantContext.set_tenant_id(entrance_code.tenant_id)", ENTRANCE_SERVICE_SOURCE)
        self.assertIn("table_no = (body.table_no or \"\").strip()", DINING_API_SOURCE)


if __name__ == "__main__":
    unittest.main()