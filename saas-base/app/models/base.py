from sqlalchemy import BigInteger, Column, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from app.utils.id_generator import generate_snowflake_id

Base = declarative_base()

class BaseModel(Base):
    __abstract__ = True
    
    id = Column(BigInteger, primary_key=True, index=True, default=generate_snowflake_id)
    tenant_id = Column(String(32), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
