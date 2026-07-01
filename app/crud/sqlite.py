# from sqlalchemy.dialects.postgresql import insert

from sqlalchemy.dialects.sqlite import insert
from models import ExchangeData1C
from sqlalchemy import func


def save_exchange(db, request):
    stmt = (
        insert(ExchangeData1C).values(
            uuid=str(request.uuid),
            amount=request.amount,
            status_1c='received',
            status_ex='received',
        )
        .on_conflict_do_update(
            index_elements=['uuid'],
            set_={
                'amount': request.amount,
                'status_1c': 'received',
                'status_ex': 'received',
                'updated_at': func.now()
            },
            where=ExchangeData1C.amount != request.amount
        )
    )
    db.execute(stmt)
    db.commit()