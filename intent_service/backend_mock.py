# backend_mock.py
from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Optional

app = FastAPI()

class ReceiveRequest(BaseModel):
    sku: str
    qty: float
    bin: str
    ref_id: Optional[str] = Field(None, alias="ref")  # akzeptiert "ref_id" ODER "ref"

    class Config:
        populate_by_name = True  # erlaubt auch "ref_id" im Body

@app.post("/api/stock/receive")
def receive(req: ReceiveRequest):
    return {"status": "ok", "received": req.model_dump(by_alias=False)}
