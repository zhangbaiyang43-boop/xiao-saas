from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta
from app.core.database import get_db
from app.core.response import RespVo
from app.core.security import create_access_token
from app.config import settings
from app.services.tenant_service import TenantService
from app.schemas.tenant import LoginRequest, RegisterRequest

router = APIRouter(prefix="/api/auth", tags=["认证"])

@router.post("/login", response_model=RespVo)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    service = TenantService(db)
    tenant = await service.get_tenant_by_phone(data.phone)
    
    if not tenant:
        return RespVo.error(code=404, msg="手机号未注册")
    if not tenant.status:
        return RespVo.error(code=403, msg="商家账号已停用")
    if data.code != "123456":
        return RespVo.error(code=400, msg="验证码错误")
    
    access_token_expires = timedelta(days=7)
    access_token = create_access_token(
        data={"tenant_id": tenant.tenant_id, "user_id": tenant.id, "role": "tenant"},
        expires_delta=access_token_expires
    )
    
    return RespVo.success(data={
        "token": access_token,
        "token_type": "bearer",
        "tenant_id": tenant.tenant_id,
        "name": tenant.name
    }, msg="ok")

@router.post("/register", response_model=RespVo)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    service = TenantService(db)
    
    existing = await service.get_tenant_by_phone(data.phone)
    if existing:
        return RespVo.error(msg="手机号已注册")
    
    from app.utils.id_generator import generate_tenant_id
    tenant_id = generate_tenant_id()
    tenant = await service.create_tenant(
        tenant_id=tenant_id,
        name=data.name,
        password_hash="",
        phone=data.phone,
        address=data.address,
        logo_url=data.logo_url,
    )
    
    return RespVo.success(data={"tenant_id": tenant.tenant_id}, msg="ok")
