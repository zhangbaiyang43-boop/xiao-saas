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
    H5_ORDER_BASE_URL: str = "https://saas.zhangbaiyang.com"
    PUBLIC_BASE_URL: str = "https://saas.zhangbaiyang.com"

    WX_SP_MCH: str = ""            
    WX_SP_API_KEY_V3: str = ""       
    WX_SP_CERT_SERIAL: str = ""      
    WX_SP_PRIVATE_KEY: str = ""      

    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

    FEIEYUN_USER: str = ""   
    FEIEYUN_UKEY: str = ""   

    PLATFORM_REGISTER_KEY: str = ""   
    SUPER_ADMIN_PASSWORD: str = ""    

    WEWORK_CORP_: str = ""
    WEWORK_AGENT_: str = ""
    WEWORK_SECRET: str = ""
    WEWORK_TOKEN: str = ""
    WEWORK_ENCODING_AES_KEY: str = ""
    WEWORK_CALLBACK_URL: str = ""
    WEWORK_STAFF_USER: str = ""
    WEWORK_TENANT_: str = ""
    
    DEBUG: bool = False
    
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
    AUTO_CREATE_TABLES: bool = True
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

settings = Settings()