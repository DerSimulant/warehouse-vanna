import os
import re
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from vanna.openai import OpenAI_Chat
from vanna.chromadb import ChromaDB_VectorStore

load_dotenv()

class MyVanna(ChromaDB_VectorStore, OpenAI_Chat):
    def __init__(self, config=None):
        ChromaDB_VectorStore.__init__(self, config=config)
        OpenAI_Chat.__init__(self, config=config)

vn = MyVanna(config={
    "api_key": os.getenv("OPENAI_API_KEY"),
    "allow_llm_to_see_data": True,   # <— hinzufügen
    # "model": "gpt-4o-mini"
})
vn.connect_to_postgres(
    host=os.getenv("PGHOST"),
    dbname=os.getenv("PGDATABASE"),
    user=os.getenv("PGUSER"),
    password=os.getenv("PGPASSWORD"),
    port=os.getenv("PGPORT"),
)

app = FastAPI(title="Vanna Warehouse", version="1.0")

class AskRequest(BaseModel):
    question: str

def is_safe_select(sql: str) -> bool:
    # trailing Semikolons entfernen
    s = re.sub(r";\s*$", "", sql.strip())
    lower = s.lower()
    # SELECT oder WITH-CTE erlauben
    if not (lower.startswith("select") or lower.startswith("with")):
        return False
    # verbotene DDL/DML Keywords hart blocken
    forbidden = r"\b(insert|update|delete|drop|alter|create|grant|revoke|truncate)\b"
    return re.search(forbidden, lower) is None



@app.post("/ask")
def ask(req: AskRequest):
    sql = vn.generate_sql(req.question, allow_llm_to_see_data=True)

    if not sql:
        raise HTTPException(status_code=400, detail="Konnte keine SQL erzeugen.")
    # Semikolon abschneiden, bevor wir prüfen/ausführen
    sql_clean = re.sub(r";\s*$", "", sql.strip())

    if not is_safe_select(sql_clean):
        raise HTTPException(status_code=400, detail=f"Nur SELECT erlaubt. (got: {sql})")
    try:
        df = vn.run_sql(sql_clean)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"SQL-Fehler: {e}")
    return {"question": req.question, "sql": sql_clean, "rows": df.to_dict(orient="records")}

