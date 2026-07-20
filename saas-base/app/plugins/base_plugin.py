from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from fastapi import APIRouter

class BasePlugin(ABC):
    metadata: Dict = {}
    
    @property
    @abstractmethod
    def plugin_code(self) -> str:
        pass
    
    @property
    def plugin_name(self) -> str:
        return self.plugin_code
    
    @property
    def description(self) -> str:
        return ""
    
    @abstractmethod
    async def install(self, tenant_id: str):
        pass
    
    @abstractmethod
    async def uninstall(self, tenant_id: str):
        pass
    
    def get_routers(self) -> List[APIRouter]:
        return []
    
    def get_frontend_pages(self) -> List[Dict]:
        return []
    
    def get_admin_config_ui(self) -> Optional[Dict]:
        return None

    def get_event_handlers(self) -> Dict:
        return {}
    
    def get_metadata(self) -> Dict:
        base = {
            "plugin_code": self.plugin_code,
            "plugin_name": self.plugin_name,
            "code": self.plugin_code,
            "name": self.plugin_name,
            "description": self.description,
            "has_frontend": len(self.get_frontend_pages()) > 0,
            "has_admin_ui": self.get_admin_config_ui() is not None
        }
        if self.metadata:
            base.update(self.metadata)
            base["plugin_code"] = base.get("code", self.plugin_code)
            base["plugin_name"] = base.get("name", self.plugin_name)
            base["has_frontend"] = len(self.get_frontend_pages()) > 0 or bool(base.get("frontend_pages"))
            base["has_admin_ui"] = self.get_admin_config_ui() is not None or bool(base.get("admin_config_ui"))
        return base
