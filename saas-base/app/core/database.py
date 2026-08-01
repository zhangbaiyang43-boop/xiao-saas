from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    engine_kwargs = {}
else:
    connect_args = {
        "init_command": "SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci",
    }
    engine_kwargs = {
        "pool_pre_ping": True,
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_recycle": settings.DB_POOL_RECYCLE,
    }
    # SQLAlchemy's MySQLDialect_asyncmy inherits pymysql's do_ping()/_send_false_to_ping
    # heuristic, which decides how to call dbapi_connection.ping() by inspecting the real
    # `pymysql` package's Connection.ping signature -- not asyncmy's. asyncmy's own adapter
    # (AsyncAdapt_asyncmy_connection.ping) requires a mandatory `reconnect` argument, so that
    # heuristic ends up calling ping() with no args and crashes with
    # "ping() missing 1 required positional argument: 'reconnect'" on every pool_pre_ping
    # checkout. Forcing the flag makes it call ping(False), which matches asyncmy's signature.
    if settings.DATABASE_URL.startswith("mysql+asyncmy"):
        from sqlalchemy.dialects.mysql.asyncmy import MySQLDialect_asyncmy
        MySQLDialect_asyncmy._send_false_to_ping = True

async_engine = create_async_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    **engine_kwargs,
)

AsyncSessionLocal = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
