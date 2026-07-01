from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db, Base, engine
from crud.sqlite import save_exchange
from schemas import ExchangeRequest
import logging

Base.metadata.create_all(bind=engine)

app = FastAPI()

@app.post("/exchange")
def exchange(request: ExchangeRequest, db: Session = Depends(get_db)):
    try:
        save_exchange(db, request)
        return {"status": "success"}
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex))

logging.basicConfig(
    filename="./logs/app.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
