"""Give the linked-Demo tenant's menu real dish photos.

The Demo menu items were seeded without images, so the mini-program falls back
to /static/order/dish-placeholder.png (the grey "?" plate). This script only
writes ONE column -- menu_items.image -- for rows of ONE tenant, matching each
dish by its exact `name`. No other columns, rows, categories, prices or
side effects are touched. Idempotent: re-running is a no-op once images match.

    cd /www/wwwroot/xiao/saas-base && source venv/bin/activate
    python scripts/fix_demo_menu.py demo                     # preview (uses IMAGE_MAP below)
    python scripts/fix_demo_menu.py demo --map demo_menu.json # preview from a JSON file
    python scripts/fix_demo_menu.py demo --map demo_menu.json --apply   # write

The mapping is  {"菜名": "图片URL"}.  URLs MUST live on a host the WeChat
mini-program is allowed to download from -- in practice the production COS
bucket `poster-system-1253573799` (…myqcloud.com). External stock-photo CDNs
(Unsplash/Pexels/图虫) are NOT in the downloadFile allowlist and render blank
in the published mini-program, so upload the files to COS first (Admin dish
edit does this for you, or drag them into the Tencent COS console) and paste
the resulting object URLs here. The mini-program appends its own
`imageMogr2/thumbnail/..` params at read time -- store the plain URL.

Edit IMAGE_MAP in place, or keep it empty and pass --map <file.json>.
The sentinel PUT_COS_URL_HERE marks entries you still have to fill.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
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
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings

PLACEHOLDER = "PUT_COS_URL_HERE"

# Recommended Demo menu: 5 categories, 12 dishes (see the script's docstring /
# the field notes). Fill each value with the COS object URL of the uploaded
# photo. Names here must match the菜品 names you create in Admin exactly.
IMAGE_MAP: dict[str, str] = {
    # 招牌
    "招牌红烧肉": PLACEHOLDER,
    "宫保鸡丁": PLACEHOLDER,
    "铁锅焖鸡": PLACEHOLDER,
    # 热菜
    "酸辣土豆丝": PLACEHOLDER,
    "西红柿炒蛋": PLACEHOLDER,
    "蒜香时蔬": PLACEHOLDER,
    # 汤品
    "番茄蛋花汤": PLACEHOLDER,
    "紫菜虾皮汤": PLACEHOLDER,
    # 主食
    "蛋炒饭": PLACEHOLDER,
    "手工牛肉面": PLACEHOLDER,
    # 饮品
    "鲜榨橙汁": PLACEHOLDER,
    "酸梅汤": PLACEHOLDER,
}


def load_map(args: list[str]) -> dict[str, str]:
    if "--map" in args:
        idx = args.index("--map")
        if idx + 1 >= len(args):
            raise SystemExit("--map 后面要跟一个 JSON 文件路径")
        path = Path(args[idx + 1]).expanduser()
        if not path.is_file():
            raise SystemExit(f"找不到映射文件: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise SystemExit("映射文件的顶层必须是 {\"菜名\": \"图片URL\"} 对象")
        return {str(k).strip(): str(v).strip() for k, v in data.items()}
    return dict(IMAGE_MAP)


def looks_like_cos(url: str) -> bool:
    return url.startswith(("http://", "https://")) and (
        "poster-system-1253573799" in url or "myqcloud.com" in url
    )


async def main() -> None:
    args = sys.argv[1:]
    apply = "--apply" in args
    positional = [a for a in args if not a.startswith("--")]
    # drop the --map value from positionals
    if "--map" in args:
        mv = args[args.index("--map") + 1] if args.index("--map") + 1 < len(args) else None
        positional = [p for p in positional if p != mv]

    tenant_id = (positional[0].strip() if positional
                 else (getattr(settings, "DEMO_TENANT_ID", "") or "").strip())
    if not tenant_id:
        raise SystemExit(
            "用法: python scripts/fix_demo_menu.py <tenant_id> [--map file.json] [--apply]\n"
            "      (不带 tenant_id 时读取 .env 的 DEMO_TENANT_ID)"
        )

    name_to_url = load_map(args)
    pending = sorted(n for n, u in name_to_url.items() if not u or u == PLACEHOLDER)
    ready = {n: u for n, u in name_to_url.items() if u and u != PLACEHOLDER}

    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        trow = (
            await conn.execute(
                sa.text("SELECT tenant_id, name FROM tenant WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            )
        ).mappings().first()
        if trow is None:
            await engine.dispose()
            raise SystemExit(f"租户不存在: tenant_id = {tenant_id}")

        dishes = (
            await conn.execute(
                sa.text("SELECT id, name, image FROM menu_items WHERE tenant_id = :tid ORDER BY sort_order, id"),
                {"tid": tenant_id},
            )
        ).mappings().all()

    print("=" * 64)
    print(f"演示租户菜品配图  tenant_id = {trow['tenant_id']}  {trow['name']!r}")
    print("=" * 64)
    print(f"菜单里现有 {len(dishes)} 个菜品；映射表提供 {len(name_to_url)} 条，其中 {len(ready)} 条已填 URL。")

    if pending:
        print("\n[待填] 这些菜名在映射表里还是占位符，本次会跳过：")
        for n in pending:
            print(f"    - {n}")

    by_name = {d["name"]: d for d in dishes}
    to_update: list[tuple[int, str, str, str]] = []  # id, name, old, new
    already_ok: list[str] = []
    for name, url in ready.items():
        d = by_name.get(name)
        if d is None:
            print(f"\n[无对应菜品] 映射表里的 {name!r} 在该租户菜单里找不到（菜名要完全一致）")
            continue
        if not looks_like_cos(url):
            print(f"\n[URL 警告] {name!r} 的图片不在 COS/myqcloud 域名下，"
                  f"发布版小程序可能加载不出来：{url}")
        if (d["image"] or "") == url:
            already_ok.append(name)
        else:
            to_update.append((d["id"], name, d["image"] or "", url))

    unmapped = [d["name"] for d in dishes if d["name"] not in name_to_url]
    if unmapped:
        print(f"\n[菜单里没配图的菜品] {len(unmapped)} 个（映射表里没有它们，保持原样）：")
        for n in unmapped:
            print(f"    - {n}")

    if already_ok:
        print(f"\n[已符合] {len(already_ok)} 个菜品的图片已经是目标 URL：{', '.join(already_ok)}")

    if not to_update:
        print("\n没有需要写入的改动。")
        await engine.dispose()
        return

    print(f"\n将更新 {len(to_update)} 个菜品的 image：")
    for _id, name, old, new in to_update:
        print(f"    {name:<10}  {old or '(空)'}  ->  {new}")

    if not apply:
        print("\n[DRY-RUN] 确认无误后加 --apply 实际写入。")
        await engine.dispose()
        return

    now = datetime.utcnow()
    async with engine.begin() as conn:
        for _id, _name, _old, new in to_update:
            await conn.execute(
                sa.text(
                    "UPDATE menu_items SET image = :img, updated_at = :now "
                    "WHERE id = :id AND tenant_id = :tid"
                ),
                {"img": new, "now": now, "id": _id, "tid": tenant_id},
            )
    await engine.dispose()

    print(f"\n[APPLIED] 已更新 {len(to_update)} 个菜品的图片。")
    print("刷新小程序菜单页即可看到（后端数据改动，无需重新构建/提审）。")


if __name__ == "__main__":
    asyncio.run(main())
