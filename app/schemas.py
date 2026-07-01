from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

class ExchangeRequest(BaseModel):
    uuid: UUID
    amount: Decimal
