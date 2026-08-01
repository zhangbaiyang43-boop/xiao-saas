from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.response import success_response, error_response
from app.core.security import get_current_user
from app.services.marketing_template_service import MarketingTemplateService

router = APIRouter(prefix="/marketing-templates", tags=["营销模"])


@router.get("/")
async def get_marketing_templates(db: AsyncSession = Depends(get_db)):
    """获取营销模列表"""
    service = MarketingTemplateService(db)
    templates = await service.get_templates()
    
    result = []
    for template in templates:
        result.append({
            "id": str(template.id),
            "template_code": template.template_code,
            "template_name": template.template_name,
            "industry": template.industry,
            "description": template.description,
            "target_customer_price_min": float(template.target_customer_price_min),
            "target_customer_price_max": float(template.target_customer_price_max),
            "status": template.status,
            "created_at": template.created_at,
            "updated_at": template.updated_at
        })
    
    return success_response(data=result)


@router.get("/merchant-templates")
async def get_merchant_templates(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user)
):
    """获取商家已启用的模列表"""
    if user.get("type") != "merchant":
        return error_response(code=401, msg="请先登录商户账号")
    tenant_id = user.get("tenant_id")

    service = MarketingTemplateService(db)
    templates = await service.get_merchant_templates(tenant_id)
    
    result = []
    for template in templates:
        result.append({
            "id": str(template.id),
            "template_id": str(template.template_id),
            "template_name": template.template.template_name if template.template else "",
            "status": template.status,
            "enabled_at": template.enabled_at,
            "created_at": template.created_at
        })
    
    return success_response(data=result)


@router.get("/{template_id}")
async def get_marketing_template_detail(
    template_id: int = Path(..., description="模"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user)
):
    """获取模详情（含则）"""
    if user.get("type") != "merchant":
        return error_response(code=401, msg="请先登录商户账号")
    service = MarketingTemplateService(db)
    template = await service.get_template_by_id(template_id)
    
    if not template:
        return error_response(code=404, msg="模不存在")
    
    rules = await service.get_template_rules(template_id)
    
    rule_list = []
    for rule in rules:
        rule_list.append({
            "id": rule.id,
            "rule_code": rule.rule_code,
            "rule_name": rule.rule_name,
            "trigger_type": rule.trigger_type,
            "coupon_type": rule.coupon_type,
            "discount_type": rule.discount_type,
            "threshold_amount": float(rule.threshold_amount),
            "discount_amount": float(rule.discount_amount),
            "valid_days": rule.valid_days,
            "trigger_delay_days": rule.trigger_delay_days,
            "sort_order": rule.sort_order,
            "status": rule.status
        })
    
    result = {
        "id": str(template.id),
        "template_code": template.template_code,
        "template_name": template.template_name,
        "industry": template.industry,
        "description": template.description,
        "target_customer_price_min": float(template.target_customer_price_min),
        "target_customer_price_max": float(template.target_customer_price_max),
        "status": template.status,
        "rules": rule_list,
        "created_at": template.created_at,
        "updated_at": template.updated_at
    }
    
    return success_response(data=result)


@router.post("/{template_id}/enable")
async def enable_marketing_template(
    template_id: int = Path(..., description="模"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user)
):
    """启用营销模"""
    if user.get("type") != "merchant":
        return error_response(code=401, msg="请先登录商户账号")
    tenant_id = user.get("tenant_id")

    service = MarketingTemplateService(db)
    
    try:
        merchant_template = await service.enable_template(tenant_id, template_id)
        return success_response(data={
            "merchant_template_id": str(merchant_template.id),
            "template_id": str(merchant_template.template_id),
            "status": merchant_template.status,
            "enabled_at": merchant_template.enabled_at
        })
    except Exception as e:
        return error_response(code=400, msg=str(e))


@router.patch("/merchant-templates/{merchant_template_id}/disable")
async def disable_merchant_template(
    merchant_template_id: int = Path(..., description="商家模"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user)
):
    """停用商家模"""
    if user.get("type") != "merchant":
        return error_response(code=401, msg="请先登录商户账号")
    tenant_id = user.get("tenant_id")

    service = MarketingTemplateService(db)
    
    try:
        merchant_template = await service.disable_template(merchant_template_id, tenant_id)
        return success_response(data={
            "merchant_template_id": str(merchant_template.id),
            "status": merchant_template.status,
            "disabled_at": merchant_template.disabled_at
        })
    except Exception as e:
        return error_response(code=400, msg=str(e))
