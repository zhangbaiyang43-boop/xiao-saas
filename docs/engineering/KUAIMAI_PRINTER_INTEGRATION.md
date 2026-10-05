# 快麦云打印对接说明

用途：记录快麦云打印的接口事实、我们代码的实际行为、已观察到的现象，以及还没验证的问题。
先看这份，再动 `saas-base/app/services/kuaimai_service.py`、`order_print_service.py` 或打印告警。

三类信息严格分开写，不要混：

- **文档**：快麦官方开放文档（`open.iot.kuaimai.com`）写明的内容。
- **代码**：本仓库现在的实际行为。
- **实测**：2026-09 在测试商户上观察到的现象。
- **未验证**：没有证据，不能当结论用。

---

## 1. 我们调用哪些接口

| 用途 | 路径 | 代码位置 |
|---|---|---|
| 小票模板打印（订单小票，主路径） | `/api/cloud/print/escTemplatePrint` | `kuaimai_service.print_template_order` |
| ESC 指令打印 | `/api/cloud/print/escWrite` | `kuaimai_service.print_order` |

- 域名 `https://cloud.kuaimai.com`，POST JSON。
- 订单模板 id 常量：`KUAIMAI_ORDER_TEMPLATE_ID`（可被租户 `kuaimai_printer.order_template_id` 覆盖）。
- 租户配置位置：`TenantConfig.business_info["printer_provider"] == "kuaimai"` 与 `business_info["kuaimai_printer"]`，必需字段只有 `app_id`、`app_secret`、`sn`（不需要 `device_key`）。
- 签名：`MD5(appSecret + 按 key 升序拼接的 key+value + appSecret)`，空值不参与，`sign` 本身不参与（`create_sign`）。

## 2. 文档里有、我们没用的接口

| 接口 | 作用 | 备注 |
|---|---|---|
| `/api/cloud/device/batchStatus` | 查设备状态，一次最多 100 台 | **所有机型可用。** 返回 `status`（ONLINE / OFFLINE / UNACTIVE / DISABLE）、`deviceStatus`（0 正常 / 1 开盖 / 2 粘纸 / 3 缺纸）、`cloudServiceExpire`（仅 4G 机型）、`waitPrintNum`（等待打印数量） |
| `/api/cloud/print/result` | 按 jobId 查打印结果 | 单次 ≤ 50 个 jobId，同一 sn 每秒 ≤ 2 次。**仅列出部分机型**：KM118DW / KM118MW / KMSX320 / KME20W / KMUL410 / KM118DG |
| 异步回调推送 | 任务到终态时快麦主动 POST 到我们的地址 | 需要公网地址；必须返回 HTTP 200 + `{"data":"OK"}`，最多推 3 次，同一 jobId 可能重复推送，要按 jobId 去重 |
| `/api/cloud/print/cancelJob` | 取消队列任务 | 所有机型 |

调用限制：单设备打印接口 QPS ≤ 6；`result` 同一 sn 每秒 ≤ 2 次（超出返回 6021）。

## 3. 返回值：两套 code，不要混

**接口业务错误码**（`code` 字段，`status=false` 时）。打印相关的：

| code | 含义 |
|---|---|
| 4001 | 序列号不存在或未激活 |
| **4005** | **设备离线** |
| 4009 | 设备密钥不正确 |
| 4015 | 签名错误 |
| 6006 | 必传参数为空 |
| 6009 | 渲染数据结构错误 |
| 6010 | 模板类型与接口不匹配 |
| 6015 | 无权限访问该模板（模板必须是该 appId 下创建的） |
| 6019 | 打印内容过大 |
| 6027 | 打印接口调用过于频繁 |

**打印任务结果码**（`result` 接口与回调里的 `code`）：

| code | 含义 |
|---|---|
| 3000 | 下发成功（任务已到达打印机） |
| 2000 | 打印成功 |
| 2007 | 打印失败 |
| 2004 | 打印异常 |
| 3001 | 打印机模式错误，打印失败 |

**我们的代码**：`_is_successful_business_response` 把 `status is True`、`success is True` 或 `code in {0, 200, 2000}` 视为成功；其他情况抛 `KuaimaiPrintError(code="KUAIMAI_BUSINESS_ERROR")`，订单进入失败 / 重试流程。所以接口一旦返回 4005，订单会进入失败路径，而不是静默成功。

## 4. 为什么 `provider_task_id` 一直是空

- **文档**：单张 `escTemplatePrint`（传 `renderData`）的成功响应是 `"data": {}`，**不含 jobId**。只有批量写法（传 `renderDataArray`，每个对象一张小票）才在 `data.jobIds` 里按顺序返回 jobId。`escWrite` 的成功响应同样没有 jobIds 字段。
- **代码**：`print_template_order` 发送的是单张写法（`renderData`），`_extract_task_id` 在响应里找不到 `taskId/printId/jobId/id`，所以 `provider_task_id` 为 `None`。
- 这是接口行为，不是解析 bug。要拿到 jobId 只能改成批量写法（哪怕只放 1 个元素）。
- **未验证**：文档说批量指令"全部渲染成功后直接写入待打印任务队列，不同步下发设备"。批量写法是否还会做同步的离线校验（返回 4005），需要实测后才能改。改之前不要假设行为一致。

## 5. 打印机离线：已知与未知

**实测（2026-09，测试商户）**：打印机断电后在小程序提交订单，后台显示出票成功（`print_status=SUCCESS`），没有任何失败提示；重新通电后，**无需任何操作**，纸自动打印出来。

**文档**：离线时 `escTemplatePrint` 可能返回 4005；`batchStatus` 可以查到 OFFLINE；`result` / 回调可以确认 2000 打印成功。

**实测与文档的矛盾，目前最可能的解释（未验证）**：云端依靠心跳判断设备在线，断电后有一段时间云端仍认为设备在线，所以接口先成功、任务进入云端队列。这个解释需要用断电实测证实：

- 断电后多久，`batchStatus` 才变成 OFFLINE？
- 云端判定离线之后再下单，接口是否返回 4005？
- 云端队列能保留多久？离线很久之后通电，旧任务是否还会打印？

**这三个问题没有答案之前**，不能声称"离线能被发现"，也不能声称"离线期间的订单一定会补打"。

打印机离线实测的方案见 `docs/prelaunch/SINGLE_STORE_PILOT_CHECKLIST.md` 第 5 节。

## 6. 只读查设备状态（运维用）

只调用 `batchStatus`，不改数据、不打印。输出里不含 appId、appSecret、sn，可以贴出来。在服务器 `saas-base` 目录用 venv 的 Python 运行（把 `0MBBUYA2` 换成目标租户 id 前缀）：

```bash
cd /www/wwwroot/xiao/saas-base && venv/bin/python - <<'PY'
import asyncio, json
from datetime import datetime, timedelta
import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
async def main():
    from app.config import settings
    from app.services.order_print_service import _load_print_route_and_credentials
    from app.services.kuaimai_service import KUAIMAI_API_BASE, create_sign, _current_timestamp
    e = create_async_engine(settings.DATABASE_URL)
    async with AsyncSession(e) as db:
        tid = (await db.execute(text("SELECT tenant_id FROM tenant WHERE tenant_id LIKE '0MBBUYA2%'"))).scalar()
        _, cred, _ = await _load_print_route_and_credentials(db, tid)
    payload = {"appId": cred["app_id"], "timestamp": _current_timestamp(), "snsStr": json.dumps([cred["sn"]])}
    payload["sign"] = create_sign(payload, cred["credential"])
    async with httpx.AsyncClient(timeout=8) as c:
        r = await c.post(KUAIMAI_API_BASE + "/api/cloud/device/batchStatus", json=payload)
    body = r.json()
    now = (datetime.utcnow() + timedelta(hours=8)).strftime("%H:%M:%S")
    if not body.get("status"):
        print(now, "查询失败 code=%s message=%s" % (body.get("code"), body.get("message")))
    else:
        names = {0: "正常", 1: "开盖", 2: "粘纸", 3: "缺纸"}
        for d in body.get("data") or []:
            print(now, "在线状态=%s" % d.get("status"), "设备状态=%s" % names.get(d.get("deviceStatus"), d.get("deviceStatus")), "等待打印数=%s" % d.get("waitPrintNum"))
    await e.dispose()
asyncio.run(main())
PY
```

规则：

- 手动运行，**不要写成循环**（同一 sn 有频率限制）。
- 终端是宝塔网页终端时，粘贴后回显可能错位，但执行是正确的，以输出为准。
- **不要贴快麦相关日志。** `[KUAIMAI_CONFIG_CHECK]` 日志会带 appId、appSecret 的前后缀。

## 7. 可能的后续工作（都未开始，都需要单独立项）

| 项 | 做法 | 前提 |
|---|---|---|
| A. 打印机健康检查 | 定时查 `batchStatus`，离线 / 缺纸 / 开盖 / 积压超过阈值时在后台显示，并走现有的打印异常短信升级 | 先完成断电实测，确认 OFFLINE 的延迟 |
| B. 取回并记录 jobId | 改成批量写法并保存 `jobIds` | 先实测批量写法在离线时的行为 |
| C. 打印结果回调 | 对外暴露回调地址，验签 / 去重，把"下发成功"升级为"打印成功" | 需要公网接口和安全评审；机型必须支持 |

## 8. 业务影响（试点相关）

- PRINT_FIRST 模式（见 `app/services/fulfilment_mode.py`）让小票成为厨房的唯一入口。打印机离线或缺纸，意味着后厨看不到单。
- 在打印机离线可被发现之前，PRINT_FIRST 只能依赖人工规则兜底（"点菜有单但没出纸，先查打印机"）。
- 文档的错误码表里没有缺纸、开盖、粘纸对应的提交错误码；这三种状态只在 `batchStatus.deviceStatus` 里有字段。缺纸时提交是否报错，没有实测，不要假设。

## 9. 取消单（拒单 / 取消时通知后厨）

订单已打印后被商家拒单或被取消，系统通过同一台打印机、同一条冻结路线再打一张取消单（`order_print_service.schedule_cancel_slip`，在 `order_lifecycle_service` 的拒单 / 取消提交之后触发）。

- **条件**：订单状态为 rejected / cancelled，并且原小票状态是 SUCCESS / UNKNOWN / SENDING，或者有过成功的手动补打。原小票从没打出的不打。受 `KITCHEN_PRINT` 能力限制，与自动出票一致。
- **不新增模板**：复用订单模板，在渲染数据里加标记。实测（2026-10）发现**店名行和订单类型行在这家店的模板里不一定印出来**，只有备注一定会印，但备注在小票靠下的位置不够醒目。所以标记还写进了**桌号**（`A1【取消】`）和**菜品列表第一行**（假菜品「【取消单·请停止制作】」，数量文字「停做」，金额 0.00，合计不变）。飞鹅云只替换标题行。
- **一单最多一张**：行锁认领，SENDING / UNKNOWN / SUCCESS 不再重发，FAILED 可以重新认领。
- **只尽力而为**：后台异步发送，失败不影响拒单。结果记在订单打印元数据 `cancel_slip`（status / error_code / provider_task_id / 时间），暴露给后台为 `cancel_slip_status`，失败时订单卡片显示红色标签。**不会自动重试，也没有短信告警。**
- **不改原小票状态**：`print_status` 与 `initial_print` 保持不变。
- **没有验证的**：不同模板下的版式。换模板或新店接入时，需要在测试订单上拒单一次，看取消单是否醒目。
