from sqlalchemy import Column, Integer, String, Numeric, DateTime
from sqlalchemy.sql import func
# from sqlalchemy.dialects.postgresql import UUID

import uuid

from database import Base

class ExchangeData1C(Base):
    __tablename__ = "exchange_data"
    id = Column(Integer, primary_key=True)
    # uuid = Column(
    #     UUID(as_uuid=True),
    #     unique=True,
    #     nullable=False,
    #     default=uuid.uuid4,
    # )
    uuid = Column(String, unique=True, nullable=False)
    amount = Column(Numeric(11,2), nullable=False)
    status_1c = Column(String(20), nullable=False)
    status_ex = Column(String(20), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())