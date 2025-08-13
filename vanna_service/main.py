import os, re
import json  # <- top of file
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
    "allow_llm_to_see_data": True,
    "model": "gpt-4o-mini",
    "temperature": 0
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
    s = re.sub(r";\s*$", "", (sql or "").strip())
    lower = s.lower()
    if not (lower.startswith("select") or lower.startswith("with")):
        return False
    forbidden = r"\b(insert|update|delete|drop|alter|create|grant|revoke|truncate)\b"
    return re.search(forbidden, lower) is None

def extract_sql(text: str) -> str:
    if not text:
        return ""
    t = text.strip()
    # Code-Fences weg
    t = re.sub(r"^```(?:sql)?", "", t, flags=re.I).strip()
    t = re.sub(r"```$", "", t, flags=re.I).strip()
    # ab WITH/SELECT schneiden
    m = re.search(r"(?is)\b(with|select)\b.*", t)
    return m.group(0).strip() if m else t

def looks_like_ledger(question: str) -> bool:
    q = (question or "").lower()
    return any(k in q for k in ["bewegung", "bewegungen", "ledger"])

def parse_limit(question: str, default=5) -> int:
    m = re.search(r"\b(letzte[nr]?|last)\s+(\d{1,3})\b", (question or "").lower())
    if m:
        try:
            n = int(m.group(2))
            if 1 <= n <= 1000:
                return n
        except:
            pass
    return default

def parse_sku(question: str) -> str | None:
    # einfache SKU-Erkennung (M4-12 etc.)
    m = re.search(r"\bsku[:\s\-]*([A-Za-z0-9._\-]+)\b", question, flags=re.I)
    if m: 
        return m.group(1)
    # Fallback: erstes Wort mit Bindestrich/Zahl
    m = re.search(r"\b([A-Za-z0-9]+[-_.][A-Za-z0-9._-]+)\b", question)
    return m.group(1) if m else None

def ledger_fallback_sql(question: str) -> str | None:
    if not looks_like_ledger(question):
        return None
    sku = parse_sku(question)
    if not sku:
        return None
    limit = parse_limit(question, default=5)
    # Handfeste, sichere SQL für “letzte N Bewegungen”
    return f"""
SELECT sl.ts, i.sku,
       fb.code AS from_bin,
       tb.code AS to_bin,
       sl.qty, sl.ref_type, sl.ref_id
FROM inventory_stockledger sl
JOIN inventory_item i ON i.id = sl.item_id
LEFT JOIN inventory_bin fb ON fb.id = sl.from_bin_id
LEFT JOIN inventory_bin tb ON tb.id = sl.to_bin_id
WHERE i.sku = '{sku}'
ORDER BY sl.ts DESC
LIMIT {limit}
""".strip()

def generate_sql_strict(question: str) -> str:
    # 0) expliziter Ledger-Fallback
    fb = ledger_fallback_sql(question)
    if fb:
        return fb

    # 1) normaler Versuch
    try:
        s1 = vn.generate_sql(question, allow_llm_to_see_data=True) or ""
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"LLM-Fehler: {e}")
    s1 = extract_sql(s1)
    if is_safe_select(s1):
        return s1

    # 2) harter Prompt
    prompt = (
        "Gib AUSSCHLIESSLICH SQL zurück. Keine Erklärungen, keine Kommentare. "
        "Beginne mit SELECT oder WITH. Ziel-DB ist PostgreSQL.\n\nFrage: " + question
    )
    try:
        s2 = vn.generate_sql(prompt, allow_llm_to_see_data=True) or ""
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"LLM-Fehler: {e}")
    s2 = extract_sql(s2)
    return s2

@app.post("/ask")
def ask(req: AskRequest):
    sql = generate_sql_strict(req.question)
    if not sql:
        raise HTTPException(status_code=400, detail="Konnte keine SQL erzeugen.")

    sql_clean = re.sub(r";\s*$", "", sql.strip())
    if not is_safe_select(sql_clean):
        raise HTTPException(status_code=400, detail=f"Nur SELECT erlaubt. (got: {sql})")

    try:
        df = vn.run_sql(sql_clean)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"SQL-Fehler: {e}")

    # 🔧 Make JSON-safe: NaN/NaT -> null, datetimes -> ISO strings
    rows = json.loads(df.to_json(orient="records", date_format="iso"))

    return {"question": req.question, "sql": sql_clean, "rows": rows}
