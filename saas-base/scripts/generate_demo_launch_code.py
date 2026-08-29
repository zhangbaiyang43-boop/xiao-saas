"""Generate the signed card entrance for the isolated linked Demo."""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from app.core.security import create_demo_launch_code


def main() -> None:
    if not settings.DEMO_TENANT_ID.strip():
        raise SystemExit("DEMO_TENANT_ID 未配置，拒绝生成体验入口")
    print(create_demo_launch_code())


if __name__ == "__main__":
    main()
