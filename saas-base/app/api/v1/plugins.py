from typing import Dict

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.core.cache_helper import clear_cache_pattern
from app.core.rate_limiter import tenant_limit
from app.core.response import RespVo, error_response, success_response
from app.core.tenant_context import TenantContext
from app.plugins.plugin_manager import plugin_manager

router = APIRouter(prefix="/api/v1/plugins", tags=["插件管理"])


class PluginCodeRequest(BaseModel):
    plugin_code: str = Field(..., description="插件编码")


class PluginConfigRequest(BaseModel):
    config: Dict = Field(default_factory=dict, description="插件配置")


def current_tenant_or_error():
    tenant_id = TenantContext.get_current_tenant_id()
    if not tenant_id:
        return None, error_response(code=401, msg="未登录或登录已过期")
    return tenant_id, None


@router.get("/lifecycle", response_model=RespVo)
@tenant_limit()
async def get_plugin_lifecycle(request: Request):
    tenant_id, error = current_tenant_or_error()
    if error:
        return error

    return success_response(data=await plugin_manager.get_lifecycle_plugins(tenant_id), msg="ok")


@router.get("/menus", response_model=RespVo)
@tenant_limit()
async def get_plugin_menus(request: Request):
    tenant_id, error = current_tenant_or_error()
    if error:
        return error

    return success_response(data=await plugin_manager.get_enabled_menus(tenant_id), msg="ok")


@router.get("/available", response_model=RespVo)
@tenant_limit()
async def get_available_plugins(request: Request):
    tenant_id, error = current_tenant_or_error()
    if error:
        return error

    return success_response(data=await plugin_manager.get_lifecycle_plugins(tenant_id), msg="ok")


@router.get("/installed", response_model=RespVo)
@tenant_limit()
async def get_installed_plugins(request: Request):
    tenant_id, error = current_tenant_or_error()
    if error:
        return error

    plugins = await plugin_manager.get_lifecycle_plugins(tenant_id)
    return success_response(data=[plugin for plugin in plugins if plugin["installed"]], msg="ok")


@router.post("/install", response_model=RespVo)
@tenant_limit()
async def install_plugin(request: Request, data: PluginCodeRequest):
    tenant_id, error = current_tenant_or_error()
    if error:
        return error

    ok, msg = await plugin_manager.install_plugin(tenant_id, data.plugin_code)
    await clear_cache_pattern("plugins:*")
    if not ok:
        return error_response(code=400, msg=msg)
    return success_response(msg=msg)


@router.post("/enable", response_model=RespVo)
@tenant_limit()
async def enable_plugin(request: Request, data: PluginCodeRequest):
    tenant_id, error = current_tenant_or_error()
    if error:
        return error

    ok, msg = await plugin_manager.enable_plugin(tenant_id, data.plugin_code)
    await clear_cache_pattern("plugins:*")
    if not ok:
        return error_response(code=400, msg=msg)
    return success_response(msg=msg)


@router.post("/disable", response_model=RespVo)
@tenant_limit()
async def disable_plugin(request: Request, data: PluginCodeRequest):
    tenant_id, error = current_tenant_or_error()
    if error:
        return error

    ok, msg = await plugin_manager.disable_plugin(tenant_id, data.plugin_code)
    await clear_cache_pattern("plugins:*")
    if not ok:
        return error_response(code=400, msg=msg)
    return success_response(msg=msg)


@router.post("/uninstall", response_model=RespVo)
@tenant_limit()
async def uninstall_plugin(request: Request, data: PluginCodeRequest):
    tenant_id, error = current_tenant_or_error()
    if error:
        return error

    ok, msg = await plugin_manager.uninstall_plugin(tenant_id, data.plugin_code)
    await clear_cache_pattern("plugins:*")
    if not ok:
        return error_response(code=400, msg=msg)
    return success_response(msg=msg)


@router.put("/{plugin_code}/config", response_model=RespVo)
@tenant_limit()
async def update_plugin_config(request: Request, plugin_code: str, data: PluginConfigRequest):
    tenant_id, error = current_tenant_or_error()
    if error:
        return error

    ok, msg = await plugin_manager.update_plugin_config(tenant_id, plugin_code, data.config)
    await clear_cache_pattern("plugins:*")
    if not ok:
        return error_response(code=400, msg=msg)
    return success_response(msg=msg)
