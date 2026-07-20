import hashlib
import json
import os


def _sign_raw(params, app_secret):
    parts = []
    for key in sorted(params.keys()):
        if key == "sign":
            continue
        value = params.get(key)
        if value is None or value == "":
            continue
        parts.append(f"{key}{value}")
    joined = "".join(parts)
    return f"{app_secret}{joined}{app_secret}"


def create_sign(params, app_secret):
    raw = _sign_raw(params, app_secret)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def test_kuaimai_sign_matches_browser_success_request():
    test_render_data = {
        "shop_name": "大宝羊肉汤",
        "queue_type_name": "中桌",
        "queue_number": "B000",
        "waiting_count": 2,
        "waiting_text": "前方等待2桌",
        "party_size": 3,
        "party_size_text": "3人",
        "estimated_wait_minutes": 15,
        "estimated_wait_text": "约15分钟",
        "created_at": "2026-07-11 10:37",
        "queue_status": "等待中",
        "queue_url": "",
        "queue_notice": "请留意现场叫号，过号请联系工作人员",
    }

    render_data_wrapped = {"排队取号": [test_render_data]}
    render_data_json = json.dumps(
        render_data_wrapped,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=False,
    )

    params = {
        "appId": "1781621428396",
        "timestamp": "2026-07-11 10:37:50",
        "sn": "UP1AD1105S000ZG",
        "templateId": "1634997391",
        "renderData": render_data_json,
    }

    app_secret = os.environ.get("KUAIMAI_APP_SECRET", "")
    expected_sign = "1e6c12591c70980d80d967bf078613c8"

    print(f"[TEST] appId={params['appId']}")
    print(f"[TEST] timestamp={params['timestamp']}")
    print(f"[TEST] sn={params['sn']}")
    print(f"[TEST] templateId={params['templateId']}")
    print(f"[TEST] renderData_length={len(render_data_json)}")
    print(f"[TEST] renderData_sha256={hashlib.sha256(render_data_json.encode('utf-8')).hexdigest()}")
    print(f"[TEST] renderData_preview={render_data_json[:200]}")
    print(f"[TEST] app_secret_length={len(app_secret)}")
    print(f"[TEST] expected_sign={expected_sign}")

    if not app_secret:
        print("\n[TEST] ERROR: KUAIMAI_APP_SECRET environment variable not set!")
        print("Please set: export KUAIMAI_APP_SECRET=your_real_app_secret")
        return False

    sign_keys = [key for key in sorted(params.keys())]
    print(f"[TEST] sign_keys={sign_keys}")

    raw_input = _sign_raw(params, app_secret)
    print(f"[TEST] raw_sign_input_length={len(raw_input)}")
    print(f"[TEST] raw_sign_input_preview={raw_input[:100]}...")

    actual_sign = create_sign(params, app_secret)
    print(f"[TEST] actual_sign={actual_sign}")

    if actual_sign == expected_sign:
        print("\n[TEST] PASSED: actual_sign matches expected_sign!")
        return True
    else:
        print("\n[TEST] FAILED: actual_sign does NOT match expected_sign!")
        print(f"[TEST] expected: {expected_sign}")
        print(f"[TEST] actual:   {actual_sign}")
        return False


if __name__ == "__main__":
    success = test_kuaimai_sign_matches_browser_success_request()
    exit(0 if success else 1)