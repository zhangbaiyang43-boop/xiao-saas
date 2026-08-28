from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    APP_NAME: str = "Multi-tenant Member Management SaaS"
    APP_VERSION: str = "1.0.0"
    
    DATABASE_URL: str = "mysql+asyncmy://root:password@localhost:3306/example_db?charset=utf8mb4"
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_ENABLED: bool = True
    REDIS_CONNECT_TIMEOUT: float = 0.2
    REDIS_SOCKET_TIMEOUT: float = 0.2

    TENCENTCLOUD_SECRET_ID: str = ""
    TENCENTCLOUD_SECRET_KEY: str = ""
    TENCENT_SMS_APP_ID: str = ""
    TENCENT_SMS_SIGN_NAME: str = ""
    TENCENT_SMS_LOGIN_TEMPLATE_ID: str = ""
    TENCENT_SMS_LOGIN_TEMPLATE_PARAM_1: str = "????"
    TENCENT_SMS_REGION: str = "ap-guangzhou"
    SMS_CODE_TTL_SECONDS: int = 300
    SMS_CODE_SEND_INTERVAL_SECONDS: int = 60
    SMS_CODE_DAILY_LIMIT: int = 10
    SMS_CODE_MAX_ATTEMPTS: int = 5
    
    JWT_SECRET_KEY: str = "your-secret-key-here-must-be-at-least-32-characters"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    
    WECHAT_APP_ID: str = ""
    WECHAT_APP_: str = ""
    WECHAT_APP_SECRET: str = ""
    # 小程序订阅消息模板 ID（微信公众平台 → 订阅消息 → 我的模板）。
    # 空字符串表示该能力未配置：前端不申请对应授权，后台也不发送。
    # 字段名（thing1/time2…）必须与选用模板时的关键词顺序一致，改模板后要同步改发送 data。
    WECHAT_COUPON_REMINDER_TEMPLATE_ID: str = "ufLleND4WNNqN-sZubt4sZP25XVaH1XSin2Dew3uwSc"
    WECHAT_QUEUE_REMINDER_TEMPLATE_ID: str = "g0qjXdu6Y76_xr7186_NRlMoolEWS9-B0XaeO5OAEpo"
    WECHAT_ORDER_SUCCESS_TEMPLATE_ID: str = "GPbNB8JgaI7zBbZZHlMtv4n9NlPBcAQSIF25dzbaD2Q"
    WECHAT_PICKUP_REMINDER_TEMPLATE_ID: str = "Z20rjKIxj2jnXswL6vVVz0dg6xNlcDpvLXb4luFBv-k"
    H5_ORDER_BASE_URL: str = "https://saas.zhangbaiyang.com"
    PUBLIC_BASE_URL: str = "https://saas.zhangbaiyang.com"

    # Platform SaaS-billing WeChat Pay merchant-of-record credentials
    # (F1G-CF-C1) -- collects 开心点单's own subscription fees. Independent
    # of Tenant.wx_* (each restaurant's own WeChat Pay account, used for
    # customer order payments) and independent of WECHAT_APP_ID (the
    # restaurant mini-program's AppID) -- neither of those is ever read as a
    # fallback for the fields below. WX_SP_MCHID (not WX_SP_MCH) is the one
    # canonical name, matching WeChat Pay's own API field name; the old
    # WX_SP_MCH name had no runtime consumer and is not kept as a
    # compatibility alias. All secrets default to "" -- production values
    # are provisioned out of band, never committed here.
    WX_SP_MCHID: str = ""
    WX_SP_APPID: str = ""
    WX_SP_API_KEY_V3: str = ""
    WX_SP_CERT_SERIAL: str = ""
    WX_SP_PRIVATE_KEY: str = ""
    # WeChat Pay public-key verification mode (the newer mode; platform-cert
    # mode is not wired up yet -- see platform_payment_config_audit()).
    WX_SP_PUBLIC_KEY_ID: str = ""
    WX_SP_PUBLIC_KEY: str = ""

    # JSAPI (certified service account, not yet registered) or MINIPROGRAM
    # (the existing certified mini-program). H5 is not eligible for this
    # platform's merchant-of-record entity type (个体工商户, confirmed
    # 2026-08 by the product owner) and must never be selectable --
    # platform_payment_config_audit() fails closed on any other value.
    SAAS_PAYMENT_MODE: str = "JSAPI"

    # Explicit, human-controlled go-live switch for real SaaS subscription
    # payment -- independent of ALLOW_MOCK_MONEY_ENDPOINTS (mock money and
    # real payment are orthogonal; neither implies or excludes the other).
    # Filling in every WX_SP_* secret above must NEVER, by itself, enable
    # real money movement: platform_payment_config_audit()'s
    # real_payment_enabled additionally requires PROVIDER_IMPLEMENTATION_READY
    # (billing_payment_provider.py), a code-level constant that env values
    # cannot flip.
    SAAS_REAL_PAYMENT_ENABLED: bool = False

    # F1G-CM: V1 SaaS subscription payment is manual-verified (official QR
    # code + platform SuperAdmin confirms receipt), not real automated WXPAY
    # -- see MANUAL_PAYMENT_PROVIDER's own docs for the full authority chain.
    # Independent of SAAS_REAL_PAYMENT_ENABLED and ALLOW_MOCK_MONEY_ENDPOINTS:
    # none of the three flags implies or excludes either of the others.
    SAAS_MANUAL_PAYMENT_ENABLED: bool = False
    # Display-only text (e.g. the receiving account holder's name) and a
    # static QR image URL (COS/CDN/static HTTPS host) -- never a secret, but
    # still never given a real value here; production values are provisioned
    # out of band. Never a base64-embedded image, never a file committed to git.
    SAAS_MANUAL_PAYMENT_PAYEE_NAME: str = ""
    SAAS_MANUAL_PAYMENT_QR_URL: str = ""
    SAAS_MANUAL_PAYMENT_CONFIRM_MINUTES: int = 10

    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

    FEIEYUN_USER: str = ""   
    FEIEYUN_UKEY: str = ""   

    PLATFORM_REGISTER_KEY: str = ""
    SUPER_ADMIN_PASSWORD: str = ""
    SUPER_ADMIN_TOTP_SECRET: str = ""
    # 商户微信支付私钥/APIv3密钥落库前的应用层加密密钥（Fernet）。
    # 用 scripts/generate_encryption_key.py 生成一把随机 key。不配置时不加密，仅用于本地开发；生产环境必须配置。
    SECRET_ENCRYPTION_KEY: str = ""

    WEWORK_CORP_ID: str = ""
    WEWORK_AGENT_ID: str = ""
    WEWORK_SECRET: str = ""
    WEWORK_TOKEN: str = ""
    WEWORK_ENCODING_AES_KEY: str = ""
    WEWORK_CALLBACK_URL: str = ""
    WEWORK_STAFF_USERID: str = ""
    WEWORK_TENANT_ID: str = ""
    
    DEBUG: bool = False
    APP_ENV: str = "development"
    # 微信 code2session mock 只能在非生产环境显式开启，生产环境配置缺失或微信异常必须失败。
    ALLOW_MOCK_WECHAT_SESSION: bool = False

    # Staff Authentication — H5 password + trusted device (formal path).
    STAFF_TRUST_DEVICE_DAYS: int = 30
    STAFF_ACCESS_TOKEN_MINUTES: int = 120
    # 核销率闭环调参总开关：关掉后 _marketing_tuning_loop 每周只计算+记日志、不写回
    # coupon_tuning（apply_tuning 仍会应用已有的覆盖层，不影响安全红线/预算闸）。
    MARKETING_AUTO_TUNING_ENABLED: bool = True
    # Cookie mode (default): HttpOnly staff_device; JSON must NOT include device_credential.
    STAFF_DEVICE_COOKIE_ENABLED: bool = True
    STAFF_DEVICE_COOKIE_NAME: str = "staff_device"
    STAFF_DEVICE_COOKIE_PATH: str = "/api"
    # 独立于 DEBUG 的开关：只有显式设为 true 才允许模拟充值/模拟支付这类会
    # 凭空产生真实余额的测试接口生效。不跟 DEBUG 绑定，因为 DEBUG 在这个项目
    # 的实际部署环境里被发现是 true，不能作为"是否在生产环境"的可靠判断依据。
    ALLOW_MOCK_MONEY_ENDPOINTS: bool = False

    RATE_LIMIT_LOGIN: str = "5/minute"
    RATE_LIMIT_PUBLIC: str = "60/minute"
    RATE_LIMIT_TENANT: str = "300/minute"
    RATE_LIMIT_JOIN: str = "20/minute"
    VERIFY_CODE_TTL_SECONDS: int = 300
    VERIFY_CODE_REFRESH_SECONDS: int = 240
    DAILY_COUPON_ISSUE_LIMIT: int = 20
    DAILY_COUPON_VERIFY_LIMIT: int = 10
    DEVICE_FREQUENCY_LIMIT: int = 30
    DEVICE_FREQUENCY_WINDOW_SECONDS: int = 60
    
    CACHE_DEFAULT_TTL: int = 1800
    CACHE_PREFIX: str = "saas:"

    PAGE_DEFAULT_LIMIT: int = 20
    PAGE_MAX_LIMIT: int = 200
    SLOW_REQUEST_MS: int = 100

    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 50
    DB_POOL_RECYCLE: int = 1800
    AUTO_CREATE_TABLES: bool = False
    CORS_ORIGINS: str = (
        "https://saas.zhangbaiyang.com,"
        "https://api.zhangbaiyang.com,"
        "http://localhost:8989,"
        "http://127.0.0.1:8989"
    )
    
    LOCK_DEFAULT_TIMEOUT: int = 10
    LOCK_RETRY_DELAY: int = 100
    
    def model_post_init(self, __context) -> None:
        if not self.WECHAT_APP_ and self.WECHAT_APP_ID:
            self.WECHAT_APP_ = self.WECHAT_APP_ID
        # JWT_SECRET_KEY signs merchant/customer/super-admin tokens alike; the
        # tutorial placeholder (with or without a "-change-in-production" suffix
        # someone forgot to actually change) must never reach a running app,
        # in any environment.
        lowered_secret = self.JWT_SECRET_KEY.lower()
        if "your-secret-key-here" in lowered_secret or "changeme" in lowered_secret:
            raise RuntimeError(
                "JWT_SECRET_KEY is still the default placeholder. Generate a real "
                "secret (e.g. `openssl rand -hex 32`) and set it in .env."
            )

settings = Settings()
