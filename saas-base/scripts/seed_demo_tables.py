"""Create the linked-Demo table pool: N entrance codes with
channel=DEMO, entry_type=table, table_no=DEMO-01..DEMO-NN, each with a
freshly generated WeChat mini-program QR image (page pages/entry/index).

Reuses EntranceCodeService.create_entrance_code -- same path the admin
backend uses -- so scene generation, the getwxacodeunlimit call and the
/static/entrance-codes/<scene>.jpg write all happen exactly as normal.

Idempotent: a DEMO table_no that already has an active code is skipped.
DRY-RUN BY DEFAULT. Pass --apply to actually create.

    cd /www/wwwroot/xiao/saas-base && source venv/bin/activate
    python /tmp/seed_demo_tables.py demo                     # preview
    python /tmp/seed_demo_tables.py demo --apply             # create 20
    python /tmp/seed_demo_tables.py demo --apply --count 24  # create 24

Requires WECHAT_APP_ID / WECHAT_APP_SECRET configured and outbound access
to api.weixin.qq.com (same as generating any normal table code). A row
whose QR call fails is committed with generation_status=FAILED and no
image_url -- it will NOT count toward the pool; re-run --apply after fixing
the cause and only the missing ones are retried.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

for _cand in (Path(__file__).resolve().parents[1], Path.cwd(), Path.cwd().parent):
    if (_cand / "app" / "config.py").is_file():
        if str(_cand) not in sys.path:
            sys.path.insert(0, str(_cand))
        break

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import sqlalchemy as sa

from app.core.database import AsyncSessionLocal
from app.models.entrance_code import EntranceCode
from app.services.entrance_code_service import EntranceCodeService


async def main() -> None:
    args = sys.argv[1:]
    apply = "--apply" in args
    count = 20
    if "--count" in args:
        try:
            count = int(args[args.index("--count") + 1])
        except (ValueError, IndexError):
            raise SystemExit("--count 后面要跟一个数字")
    positional = [a for a in args if not a.startswith("--") and not a.isdigit()]
    if not positional:
        raise SystemExit("用法: python scripts/seed_demo_tables.py <tenant_id> [--apply] [--count 20]")
    tenant_id = positional[0].strip()
    table_nos = [f"DEMO-{i:02d}" for i in range(1, count + 1)]

    async with AsyncSessionLocal() as db:
        tenant_name = (
            await db.execute(sa.text("SELECT name FROM tenant WHERE tenant_id = :t"), {"t": tenant_id})
        ).scalar_one_or_none()
        if tenant_name is None:
            raise SystemExit(f"租户不存在: tenant_id = {tenant_id}")

        existing = set(
            (
                await db.execute(
                    sa.select(EntranceCode.table_no).where(
                        EntranceCode.tenant_id == tenant_id,
                        EntranceCode.channel == "DEMO",
                        EntranceCode.entry_type == "table",
                        EntranceCode.status == 1,
                    )
                )
            ).scalars().all()
        )
        existing = {(t or "").strip() for t in existing}
        todo = [t for t in table_nos if t not in existing]

        print("=" * 60)
        print(f"租户  {tenant_id}  {tenant_name!r}")
        print(f"目标 {count} 张：{table_nos[0]} .. {table_nos[-1]}")
        print(f"已存在可用 DEMO 桌码 {len(existing & set(table_nos))} 张，需新建 {len(todo)} 张")
        print("=" * 60)

        if not todo:
            print("已齐，无需新建。")
            return

        if not apply:
            print("[DRY-RUN] 将新建：", ", ".join(todo))
            print("确认后加 --apply。")
            return

        svc = EntranceCodeService(db)
        svc.set_tenant_id(tenant_id)
        ok, failed = 0, 0
        for t_no in todo:
            try:
                code = await svc.create_entrance_code(
                    name=f"演示桌 {t_no}",
                    channel="DEMO",
                    table_no=t_no,
                    entry_type="table",
                    order_mode="dine_in",
                )
                status = code.generation_status
                if status == "SUCCESS" and code.image_url:
                    ok += 1
                    print(f"  {t_no}  OK    scene={code.scene}  {code.image_url}")
                else:
                    failed += 1
                    print(f"  {t_no}  码已建但图失败  status={status}  err={code.generation_error}")
            except Exception as exc:
                failed += 1
                print(f"  {t_no}  失败  {exc!r}")

        print("=" * 60)
        print(f"新建成功 {ok} 张，图片失败 {failed} 张。")
        if failed:
            print("修好微信码生成后再跑一次 --apply，只会补失败的那些。")
        print("再跑 check_demo_tenant.py 复核。")


if __name__ == "__main__":
    asyncio.run(main())
