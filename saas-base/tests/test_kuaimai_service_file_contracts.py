import importlib.util
import json
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "app" / "services" / "kuaimai_service.py"
SPEC = importlib.util.spec_from_file_location("kuaimai_service_file", MODULE_PATH)
kuaimai_service = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(kuaimai_service)


def make_order(**overrides):
    data = {
        "id": 7482068958623961088,
        "table_no": "A01",
        "created_at": None,
        "total": 0.01,
        "discount_amount": 0,
        "payment_method": "wxpay",
        "remark": "",
    }
    data.update(overrides)
    return type("OrderObj", (), data)()


def make_item(**overrides):
    data = {
        "name": "测试菜品",
        "qty": 1,
        "price": 0.01,
    }
    data.update(overrides)
    return type("OrderItemObj", (), data)()


class KuaimaiServiceFileContractsTest(unittest.TestCase):
    def test_create_sign_returns_lowercase_md5(self):
        sign = kuaimai_service.create_sign(
            {
                "appId": "123456",
                "sn": "KM110h45932",
                "timestamp": "2020-10-10 15:29:29",
            },
            "abc",
        )
        self.assertEqual(sign, sign.lower())

    def test_create_sign_excludes_share_code_by_default(self):
        params = {
            "appId": "123456",
            "copies": 1,
            "shareCode": "Z7MTLK",
            "sn": "KM110h45932",
            "timestamp": "2020-10-10 15:29:29",
        }
        self.assertEqual(
            kuaimai_service.create_sign(params, "abc"),
            kuaimai_service.build_sign_variants(params, "abc")["compact_without_share_code"],
        )

    def test_build_template_print_payload_serializes_render_data_and_signs(self):
        payload = kuaimai_service.build_template_print_payload(
            app_id="123456",
            app_secret="abc",
            sn="KM110h45932",
            template_id="1634997391",
            render_data={"shop_name": "Demo", "queue_number": "A018"},
            timestamp="2020-10-10 15:29:29",
        )
        self.assertEqual(payload["templateId"], "1634997391")
        self.assertEqual(payload["renderData"], '{"shop_name":"Demo","queue_number":"A018"}')
        self.assertEqual(payload["sign"], kuaimai_service.create_sign(payload, "abc"))

    def test_order_template_render_data_includes_standard_items_fields(self):
        order = make_order()
        item = make_item()

        render_data = kuaimai_service.build_order_template_render_data(order, [item], shop_name="测试门店")

        self.assertEqual(render_data["shop_name"], "测试门店")
        self.assertEqual(render_data["pay_type"], "微信支付")
        self.assertEqual(render_data["pay_type_text"], "微信支付")
        self.assertNotIn("goods", render_data)
        self.assertNotIn("商品明细", render_data)
        self.assertNotIn("点餐订单", render_data)
        row = render_data["items"][0]
        self.assertEqual(row["goods_name"], "测试菜品")
        self.assertEqual(row["display_name"], "测试菜品")
        self.assertEqual(row["quantity"], 1)
        self.assertEqual(row["quantity_text"], "×1")
        self.assertEqual(row["unit_price"], "0.01")
        self.assertEqual(row["item_amount"], "0.01")
        self.assertEqual(row["item_amount_text"], "0.01")
        self.assertEqual(row["sku_text"], "")
        self.assertEqual(row["option_text"], "")
        self.assertEqual(row["addons"], "")
        self.assertNotIn("item_remark", row)

    def test_template_payload_render_data_contains_items_and_goods_arrays(self):
        render_data = {
            "order_no": "7482068958623961088",
            "table_no": "A01",
            "pickup_no": "15",
            "total_amount": "15.00",
            "pay_amount": "15.00",
            "pay_type": "balance",
            "pay_type_text": "余额支付",
            "items": [{
                "goods_name": "牛肉汤",
                "display_name": "牛肉汤",
                "quantity": 1,
                "quantity_text": "×1",
                "unit_price": "15.00",
                "item_amount": "15.00",
                "item_amount_text": "15.00",
                "sku_text": "",
                "option_text": "",
                "addons": "",
                "item_remark": "",
            }],
        }

        payload = kuaimai_service.build_template_print_payload(
            app_id="123456",
            app_secret="abc",
            sn="KM110h45932",
            template_id="1634998374",
            render_data=render_data,
            timestamp="2020-10-10 15:29:29",
        )
        final_render_data = json.loads(payload["renderData"])

        self.assertIsInstance(final_render_data["items"], list)
        self.assertIsInstance(final_render_data["goods"], list)
        self.assertIn("点餐订单", final_render_data)
        self.assertIsInstance(final_render_data["点餐订单"], list)
        self.assertEqual(final_render_data["点餐订单"][0]["order_no"], "7482068958623961088")
        self.assertEqual(final_render_data["点餐订单"][0]["table_no"], "A01")
        self.assertEqual(final_render_data["点餐订单"][0]["pickup_no"], "15")
        self.assertEqual(final_render_data["点餐订单"][0]["total_amount"], "15.00")
        self.assertEqual(final_render_data["点餐订单"][0]["pay_amount"], "15.00")
        self.assertEqual(final_render_data["点餐订单"][0]["pay_type"], "余额支付")
        self.assertEqual(final_render_data["点餐订单"][0]["items"][0]["goods_name"], "牛肉汤")
        self.assertEqual(final_render_data["items"][0]["goods_name"], "牛肉汤")
        self.assertEqual(final_render_data["items"][0]["quantity_text"], "×1")
        self.assertEqual(final_render_data["items"][0]["item_amount_text"], "15.00")
        self.assertEqual(final_render_data["goods"][0]["goods_name"], "牛肉汤")
        self.assertEqual(final_render_data["goods"][0]["quantity_text"], "×1")
        self.assertEqual(final_render_data["goods"][0]["item_amount_text"], "15.00")
        self.assertEqual(final_render_data["pay_type"], "余额支付")
        self.assertEqual(final_render_data["pay_type_text"], "余额支付")

    def test_order_template_render_data_formats_specs_and_remark(self):
        order = make_order(table_no="B02", total=15.5, discount_amount=2, payment_method="wechat_pay", remark="先上汤")
        item = make_item(
            name="宫保鸡丁",
            qty=1,
            price=15.5,
            sku_text="大份",
            option_text="微辣",
            addons="",
            item_remark="不要花生",
        )

        render_data = kuaimai_service.build_order_template_render_data(order, [item])
        row = render_data["items"][0]

        self.assertEqual(render_data["total_amount"], "17.50")
        self.assertEqual(render_data["discount_amount"], "2.00")
        self.assertEqual(render_data["pay_amount"], "15.50")
        self.assertIn("大份 / 微辣", row["display_name"])
        self.assertIn("备注：不要花生", row["display_name"])
        self.assertNotIn("item_remark", row)
        self.assertEqual(json.dumps(render_data, ensure_ascii=False).count("不要花生"), 1)

    def test_order_template_validation_rejects_empty_items(self):
        render_data = {
            "order_no": "1234",
            "table_no": "A01",
            "items": [],
            "total_amount": "1.00",
            "pay_amount": "1.00",
        }

        valid, error_code = kuaimai_service.validate_order_template_render_data(render_data)

        self.assertFalse(valid)
        self.assertEqual(error_code, "PRINT_ITEMS_PAYLOAD_INVALID")

    def test_order_template_render_data_supports_twenty_items(self):
        order = make_order(total=20, payment_method="cash")
        items = [make_item(name=f"菜品{i}", qty=1, price=1) for i in range(20)]

        render_data = kuaimai_service.build_order_template_render_data(order, items)
        valid, error_code = kuaimai_service.validate_order_template_render_data(render_data)

        self.assertTrue(valid, error_code)
        self.assertEqual(len(render_data["items"]), 20)
        self.assertIsInstance(render_data["items"], list)
        self.assertEqual(render_data["items"][0]["item_amount_text"], "1.00")
        payload = kuaimai_service.build_template_print_payload(
            "123456",
            "abc",
            "KM110h45932",
            "1634998374",
            render_data,
            timestamp="2020-10-10 15:29:29",
        )
        final_render_data = json.loads(payload["renderData"])
        self.assertEqual(len(final_render_data["items"]), 20)
        self.assertEqual(len(final_render_data["goods"]), 20)
        self.assertEqual(final_render_data["goods"][19]["goods_name"], final_render_data["items"][19]["goods_name"])
        self.assertEqual(render_data["pay_type"], "现金")
        self.assertEqual(render_data["pay_type_text"], "现金")

    def test_order_template_payload_covers_print_edge_cases(self):
        remark = "不要辣，打包，米饭分开放"
        long_name = "番茄鸡蛋面加长菜名测试超过正常宽度仍应打印完整"
        order = make_order(
            id=7482068958623961099,
            table_no="A08",
            total=150.75,
            discount_amount=3,
            payment_method="wxpay",
            remark=remark,
        )
        items = [
            make_item(name="牛肉汤", qty=12, price=10),
            make_item(name=long_name, qty=1, price=20.75),
            make_item(name="米饭", qty=10, price=1),
        ]

        render_data = kuaimai_service.build_order_template_render_data(order, items, shop_name="味来餐厅")
        payload = kuaimai_service.build_template_print_payload(
            app_id="123456",
            app_secret="abc",
            sn="KM110h45932",
            template_id="1634998374",
            render_data=render_data,
            timestamp="2020-10-10 15:29:29",
        )
        final_render_data = json.loads(payload["renderData"])

        self.assertEqual(payload["templateId"], "1634998374")
        self.assertEqual(final_render_data["shop_name"], "味来餐厅")
        self.assertEqual(final_render_data["remark"], remark)
        self.assertEqual(len(final_render_data["items"]), 3)
        self.assertEqual(len(final_render_data["goods"]), 3)
        self.assertEqual(final_render_data["items"][0]["quantity_text"], "×12")
        self.assertEqual(final_render_data["items"][0]["item_amount_text"], "120.00")
        self.assertEqual(final_render_data["goods"][0], {
            "goods_name": "牛肉汤",
            "quantity_text": "×12",
            "item_amount_text": "120.00",
        })
        self.assertEqual(final_render_data["items"][1]["goods_name"], long_name)
        self.assertEqual(final_render_data["goods"][1]["goods_name"], long_name)
        self.assertEqual(final_render_data["pay_type"], "微信支付")
        self.assertEqual(final_render_data["pay_type_text"], "微信支付")

    def test_balance_payment_maps_to_chinese_text(self):
        order = make_order(payment_method="balance")
        item = make_item()

        render_data = kuaimai_service.build_order_template_render_data(order, [item])

        self.assertEqual(render_data["pay_type"], "余额支付")
        self.assertEqual(render_data["pay_type_text"], "余额支付")

    def test_business_success_accepts_boolean_status(self):
        self.assertTrue(kuaimai_service._is_successful_business_response({"status": True}))

    def test_business_success_accepts_numeric_code_shape(self):
        self.assertTrue(kuaimai_service._is_successful_business_response({"code": 2000, "msg": "ok"}))
        self.assertTrue(kuaimai_service._is_successful_business_response({"code": "2000", "msg": "ok"}))

    def test_extract_task_id_supports_nested_and_flat_shapes(self):
        self.assertEqual(
            kuaimai_service._extract_task_id({"data": {"taskId": "abc123"}}),
            "abc123",
        )
        self.assertEqual(
            kuaimai_service._extract_task_id({"jobId": 931}),
            "931",
        )


if __name__ == "__main__":
    unittest.main()
