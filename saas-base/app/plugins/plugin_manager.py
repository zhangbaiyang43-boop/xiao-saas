import importlib
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from fastapi import FastAPI
from sqlalchemy import select

from app.core.database import get_db
from app.core.events import DomainEvent
from app.models.tenant_plugin import TenantPlugin
from app.plugins.base_plugin import BasePlugin


REQUIRED_METADATA_FIELDS = ["code", "name", "version", "entry"]
PLUGIN_STATUS_NOT_INSTALLED = "NOT_INSTALLED"
PLUGIN_STATUS_INSTALLED_DISABLED = "INSTALLED_DISABLED"
PLUGIN_STATUS_ENABLED = "ENABLED"
PLUGIN_STATUS_ERROR = "ERROR"


class PluginManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.plugins: Dict[str, BasePlugin] = {}
            cls._instance.metadata: Dict[str, Dict] = {}
            cls._instance.app: FastAPI = None
        return cls._instance

    def register_app(self, app: FastAPI):
        self.app = app

    def register(self, plugin: BasePlugin, metadata: Dict | None = None):
        if metadata:
            plugin.metadata = metadata
            self.metadata[plugin.plugin_code] = metadata

        self.plugins[plugin.plugin_code] = plugin

        if self.app:
            for router in plugin.get_routers():
                self.app.include_router(router)

    def discover_plugin_metadata(self, plugins_dir: str = "app/plugins") -> List[Dict]:
        root = Path(plugins_dir)
        if not root.exists():
            return []

        discovered = []
        for plugin_dir in sorted(root.iterdir(), key=lambda item: item.name):
            if not plugin_dir.is_dir() or plugin_dir.name.startswith(".") or plugin_dir.name == "__pycache__":
                continue

            metadata_file = plugin_dir / "plugin.json"
            if not metadata_file.exists():
                continue

            metadata = self._read_metadata(metadata_file, plugin_dir)
            if metadata:
                discovered.append(metadata)

        return discovered

    def load_plugins(self, plugins_dir: str = "app/plugins", package_prefix: str = "app.plugins"):
        for metadata in self.discover_plugin_metadata(plugins_dir):
            self._load_plugin(metadata, package_prefix)

    def _read_metadata(self, metadata_file: Path, plugin_dir: Path) -> Dict | None:
        try:
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Failed to read plugin metadata {metadata_file}: {exc}")
            return None

        missing = [field for field in REQUIRED_METADATA_FIELDS if not metadata.get(field)]
        if missing:
            print(f"Plugin metadata {metadata_file} missing fields: {', '.join(missing)}")
            return None

        entry = plugin_dir / metadata["entry"]
        if not entry.exists():
            print(f"Plugin entry not found: {entry}")
            return None

        normalized = {
            "plugin_code": metadata["code"],
            "plugin_name": metadata["name"],
            "description": metadata.get("description", ""),
            "category": metadata.get("category", "general"),
            "enabled_by_default": bool(metadata.get("enabled_by_default", False)),
            "dependencies": metadata.get("dependencies", metadata.get("depends_on", [])),
            "depends_on": metadata.get("depends_on", metadata.get("dependencies", [])),
            "routes": metadata.get("routes", []),
            "permissions": metadata.get("permissions", []),
            "admin_menu": metadata.get("admin_menu"),
            "config_schema": metadata.get("config_schema", []),
            "plugin_dir": str(plugin_dir),
            **metadata,
        }
        normalized["dependencies"] = normalized.get("dependencies") or normalized.get("depends_on") or []
        normalized["depends_on"] = normalized["dependencies"]
        return normalized

    def _load_plugin(self, metadata: Dict, package_prefix: str):
        plugin_code = metadata["code"]
        module_path = f"{package_prefix}.{plugin_code}"
        try:
            plugin_module = importlib.import_module(module_path)
            if hasattr(plugin_module, "get_plugin"):
                plugin = plugin_module.get_plugin()
                if isinstance(plugin, BasePlugin):
                    self.register(plugin, metadata)
        except Exception as exc:
            print(f"Failed to load plugin {plugin_code}: {exc}")

    def get_all_plugins(self) -> List[BasePlugin]:
        return list(self.plugins.values())

    def get_all_metadata(self) -> List[Dict]:
        return [plugin.get_metadata() for plugin in self.get_all_plugins()]

    def get_plugin(self, plugin_code: str) -> BasePlugin | None:
        return self.plugins.get(plugin_code)

    @staticmethod
    def parse_config(config_json: str | None) -> dict:
        if not config_json:
            return {}
        try:
            value = json.loads(config_json)
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def default_config(metadata: Dict) -> dict:
        config = {}
        for item in metadata.get("config_schema") or []:
            key = item.get("key")
            if key:
                config[key] = item.get("default")
        return config

    def build_lifecycle_item(self, metadata: Dict, tenant_record: TenantPlugin | None, enabled_codes: set[str]) -> Dict:
        plugin_code = metadata["plugin_code"]
        dependencies = metadata.get("dependencies") or []
        missing_dependencies = [code for code in dependencies if code not in enabled_codes]
        record_config = self.parse_config(getattr(tenant_record, "config_json", None))
        config = {**self.default_config(metadata), **record_config}

        if tenant_record:
            lifecycle_status = tenant_record.lifecycle_status or (
                PLUGIN_STATUS_ENABLED if tenant_record.status == 1 else PLUGIN_STATUS_INSTALLED_DISABLED
            )
        else:
            lifecycle_status = PLUGIN_STATUS_NOT_INSTALLED

        return {
            **metadata,
            "plugin_code": plugin_code,
            "plugin_name": metadata.get("plugin_name") or metadata.get("name") or plugin_code,
            "version": metadata.get("version", "0.0.0"),
            "installed": tenant_record is not None,
            "enabled": lifecycle_status == PLUGIN_STATUS_ENABLED,
            "lifecycle_status": lifecycle_status,
            "installed_version": getattr(tenant_record, "version", None),
            "config": config,
            "last_error": getattr(tenant_record, "last_error", None),
            "installed_at": getattr(tenant_record, "installed_at", None),
            "enabled_at": getattr(tenant_record, "enabled_at", None),
            "disabled_at": getattr(tenant_record, "disabled_at", None),
            "dependencies_met": not missing_dependencies,
            "missing_dependencies": missing_dependencies,
        }

    def build_enabled_menus(self, metadata_items: List[Dict], record_map: Dict[str, TenantPlugin]) -> List[Dict]:
        menus = []
        for metadata in metadata_items:
            plugin_code = metadata["plugin_code"]
            record = record_map.get(plugin_code)
            if not record or record.status != 1 or record.lifecycle_status != PLUGIN_STATUS_ENABLED:
                continue
            admin_menu = metadata.get("admin_menu")
            if not admin_menu:
                continue
            menus.append({
                "plugin_code": plugin_code,
                "title": admin_menu.get("title") or metadata.get("plugin_name") or metadata.get("name"),
                "path": admin_menu.get("path") or f"/plugin/{plugin_code}",
                "icon": admin_menu.get("icon") or "Platform",
            })
        return menus

    async def get_tenant_plugin_record_map(self, tenant_id: str) -> Dict[str, TenantPlugin]:
        result = {}
        async for db in get_db():
            rows = await db.execute(select(TenantPlugin).filter(TenantPlugin.tenant_id == tenant_id))
            result = {row.plugin_code: row for row in rows.scalars().all()}
        return result

    async def get_lifecycle_plugins(self, tenant_id: str) -> List[Dict]:
        metadata_items = self.get_all_metadata()
        record_map = await self.get_tenant_plugin_record_map(tenant_id)
        enabled_codes = {
            code for code, record in record_map.items()
            if record.status == 1 and record.lifecycle_status == PLUGIN_STATUS_ENABLED
        }
        return [
            self.build_lifecycle_item(metadata, record_map.get(metadata["plugin_code"]), enabled_codes)
            for metadata in metadata_items
        ]

    async def get_enabled_menus(self, tenant_id: str) -> List[Dict]:
        return self.build_enabled_menus(self.get_all_metadata(), await self.get_tenant_plugin_record_map(tenant_id))

    async def install_plugin(self, tenant_id: str, plugin_code: str) -> tuple[bool, str]:
        plugin = self.get_plugin(plugin_code)
        metadata = self.metadata.get(plugin_code)
        if not plugin or not metadata:
            return False, "插件不存在"

        async for db in get_db():
            result = await db.execute(select(TenantPlugin).filter(TenantPlugin.tenant_id == tenant_id, TenantPlugin.plugin_code == plugin_code))
            record = result.scalar_one_or_none()
            if record:
                return False, "插件已安装"

            record = TenantPlugin(
                tenant_id=tenant_id,
                plugin_code=plugin_code,
                status=0,
                lifecycle_status=PLUGIN_STATUS_INSTALLED_DISABLED,
                version=metadata.get("version"),
                config_json=json.dumps(self.default_config(metadata), ensure_ascii=False),
                installed_at=datetime.utcnow(),
            )
            db.add(record)
            await db.commit()
        return True, "安装成功"

    async def enable_plugin(self, tenant_id: str, plugin_code: str) -> tuple[bool, str]:
        plugin = self.get_plugin(plugin_code)
        metadata = self.metadata.get(plugin_code)
        if not plugin or not metadata:
            return False, "插件不存在"

        async for db in get_db():
            result = await db.execute(select(TenantPlugin).filter(TenantPlugin.tenant_id == tenant_id, TenantPlugin.plugin_code == plugin_code))
            record = result.scalar_one_or_none()
            if not record:
                return False, "插件未安装"

            enabled_codes = set(await self.get_tenant_plugins_from_db(db, tenant_id))
            missing = [code for code in metadata.get("dependencies", []) if code not in enabled_codes]
            if missing:
                record.lifecycle_status = PLUGIN_STATUS_ERROR
                record.last_error = f"缺少依赖插件：{', '.join(missing)}"
                await db.commit()
                return False, record.last_error

            try:
                await plugin.install(tenant_id)
                record.status = 1
                record.lifecycle_status = PLUGIN_STATUS_ENABLED
                record.version = metadata.get("version")
                record.last_error = None
                record.enabled_at = datetime.utcnow()
                await db.commit()
            except Exception as exc:
                record.status = 0
                record.lifecycle_status = PLUGIN_STATUS_ERROR
                record.last_error = str(exc)
                await db.commit()
                return False, f"启用失败：{exc}"
        return True, "启用成功"

    async def disable_plugin(self, tenant_id: str, plugin_code: str) -> tuple[bool, str]:
        plugin = self.get_plugin(plugin_code)
        if not plugin:
            return False, "插件不存在"

        async for db in get_db():
            result = await db.execute(select(TenantPlugin).filter(TenantPlugin.tenant_id == tenant_id, TenantPlugin.plugin_code == plugin_code))
            record = result.scalar_one_or_none()
            if not record:
                return False, "插件未安装"

            try:
                await plugin.uninstall(tenant_id)
                record.status = 0
                record.lifecycle_status = PLUGIN_STATUS_INSTALLED_DISABLED
                record.last_error = None
                record.disabled_at = datetime.utcnow()
                await db.commit()
            except Exception as exc:
                record.lifecycle_status = PLUGIN_STATUS_ERROR
                record.last_error = str(exc)
                await db.commit()
                return False, f"禁用失败：{exc}"
        return True, "禁用成功"

    async def uninstall_plugin(self, tenant_id: str, plugin_code: str) -> tuple[bool, str]:
        plugin = self.get_plugin(plugin_code)
        if not plugin:
            return False, "插件不存在"

        async for db in get_db():
            result = await db.execute(select(TenantPlugin).filter(TenantPlugin.tenant_id == tenant_id, TenantPlugin.plugin_code == plugin_code))
            record = result.scalar_one_or_none()
            if not record:
                return False, "插件未安装"

            if record.status == 1:
                await plugin.uninstall(tenant_id)
            await db.delete(record)
            await db.commit()
        return True, "卸载成功"

    async def update_plugin_config(self, tenant_id: str, plugin_code: str, config: Dict) -> tuple[bool, str]:
        metadata = self.metadata.get(plugin_code)
        if not metadata:
            return False, "插件不存在"

        allowed_keys = {item.get("key") for item in metadata.get("config_schema", []) if item.get("key")}
        sanitized = {key: value for key, value in config.items() if not allowed_keys or key in allowed_keys}
        merged = {**self.default_config(metadata), **sanitized}

        async for db in get_db():
            result = await db.execute(select(TenantPlugin).filter(TenantPlugin.tenant_id == tenant_id, TenantPlugin.plugin_code == plugin_code))
            record = result.scalar_one_or_none()
            if not record:
                return False, "插件未安装"
            record.config_json = json.dumps(merged, ensure_ascii=False)
            await db.commit()
        return True, "配置已保存"

    async def get_tenant_plugins(self, tenant_id: str) -> List[str]:
        result = []
        async for db in get_db():
            result = await self.get_tenant_plugins_from_db(db, tenant_id)

        return result

    async def get_tenant_plugins_from_db(self, db, tenant_id: str) -> List[str]:
        tenant_plugins = await db.execute(
            select(TenantPlugin).filter(
                TenantPlugin.tenant_id == tenant_id,
                TenantPlugin.status == 1,
                TenantPlugin.lifecycle_status == PLUGIN_STATUS_ENABLED,
            )
        )
        return [tp.plugin_code for tp in tenant_plugins.scalars().all()]

    async def dispatch_event(self, event: DomainEvent) -> List[Dict]:
        if not event.tenant_id:
            return []

        enabled_codes = await self.get_tenant_plugins_from_db(event.db, event.tenant_id) if event.db else await self.get_tenant_plugins(event.tenant_id)
        results = []
        for plugin_code in enabled_codes:
            plugin = self.get_plugin(plugin_code)
            if not plugin:
                continue
            handler = plugin.get_event_handlers().get(event.name)
            if not handler:
                continue
            try:
                data = await handler(event)
                results.append({"plugin": plugin_code, "event": event.name, "status": "ok", "data": data})
            except Exception as exc:
                results.append({"plugin": plugin_code, "event": event.name, "status": "error", "error": str(exc)})
        return results


plugin_manager = PluginManager()
