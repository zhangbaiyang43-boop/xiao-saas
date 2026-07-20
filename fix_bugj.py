# -*- coding: utf-8 -*-
"""BUG-J: Line-number-based replacement of garbled Chinese in miniapp.py."""
import sys

path = r"C:\Users\15936\Desktop\xiao\saas-base\app\api\v1\miniapp.py"

with open(path, "rb") as f:
    raw = f.read()

lines = raw.split(b"\n")

# {1-indexed line number: clean line bytes WITHOUT any trailing \r or \n}
# All clean strings are UTF-8 encoded by Python since this script is UTF-8.
def u(s):
    return s.encode("utf-8")

target_lines = {
    165: u('        logger.info(f"entry_join 请求 - scene: {data.scene}, phone: {data.phone}")'),
    174: u('                logger.warning(f"入口码无效或已停用 - scene: {data.scene}")'),
    177: u('            logger.info(f"通过入口码找到租户 - tenant_id: {tenant_id}")'),
    180: u('            logger.info(f"通过 tenant_id 直接入会 - tenant_id: {tenant_id}, invite_code: {data.invite_code}")'),
    182: u('            return error_response(code=400, msg="缺少入口码或商家信息，请重新扫码")'),
    187: u('            logger.warning(f"商家不存在或已停用 - tenant_id: {tenant_id}")'),
    192: u('        # 用 code 换取 openid'),
    197: u('        logger.info(f"微信 code2session 结果 - openid: {openid}, unionid: {unionid}")'),
    200: u('            logger.error("微信登录失败，未获取到 openid")'),
    208: u('                logger.warning(f"手机号获取失败 - error: {phone_error}")'),
    209: u('                return error_response(code=400, msg="手机号获取失败，请重试或手动输入手机号")'),
    250: u('                        f"当前 customer.openid 已被其他会员占用，跳过更新 - "'),
    254: u('                logger.info(f"更新会员信息 - customer_id: {existing_customer.id}, update_data: {update_data}")'),
    281: u('            logger.info(f"手机号找到会员 - customer_id: {customer.id}, phone: {data.phone}")'),
    284: u('                    f"手机号已切换会员，openid 从旧会员迁移到当前手机号会员 - "'),
    308: u('            logger.info(f"重绑 identity（已有会员）- customer_id: {customer.id}, openid: {openid}")'),
    317: u('                    f"openid 已绑定到其他会员，当前用手机号注册新会员 - "'),
    345: u('            logger.info(f"新会员已创建 - customer_id: {customer.id}, is_new_customer: {is_new_customer}")'),
    347: u('            # 绑定 identity'),
    355: u('            logger.info(f"重绑 identity（新会员）- customer_id: {customer.id}, openid: {openid}")'),
    361: u('        logger.info(f"确认会员 ID - customer_id: {customer.id}")'),
    363: u('        # 生成 token'),
    365: u('        logger.info(f"生成 token 完成 - customer_id: {customer.id}")'),
    380: u('            logger.info(f"已有新人券，跳过发放 - customer_id: {customer.id}, coupon_id: {existing_welcome_coupon.id}")'),
    405: u('                    logger.info(f"新人券发放成功 - customer_id: {customer.id}, coupon_data: {coupon_data}")'),
    408: u('                    logger.info(f"新人券未发放 - customer_id: {customer.id}, coupon_result: {coupon_result}")'),
    412: u('                logger.exception(f"新人券发放异常，已回滚券相关事务 - customer_id: {customer_id_for_log}, error: {coupon_error}")'),
    413: u('        logger.info(f"入会完成 - customer_id: {customer.id}, tenant_id: {tenant_id}, is_new_customer: {is_new_customer}")'),
    455: u('        logger.exception(f"entry_join 顶层异常 - scene: {data.scene}, phone: {data.phone}, error: {str(e)}")'),
}

count = 0
for line_no in sorted(target_lines):
    idx = line_no - 1
    if idx >= len(lines):
        sys.stdout.buffer.write(b"L" + str(line_no).encode() + b": OUT OF RANGE\n")
        continue
    original = lines[idx]
    clean = target_lines[line_no]
    # Preserve \r if original had CRLF
    if original.endswith(b"\r"):
        clean = clean + b"\r"
    lines[idx] = clean
    count += 1
    sys.stdout.buffer.write(b"L" + str(line_no).encode() + b": OK\n")

with open(path, "wb") as f:
    f.write(b"\n".join(lines))

sys.stdout.buffer.write(b"\nDone. " + str(count).encode() + b"/" + str(len(target_lines)).encode() + b" lines replaced.\n")
