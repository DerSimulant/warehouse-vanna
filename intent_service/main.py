import os, json, requests
from typing import Optional, Literal
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
app = FastAPI(title="Warehouse Intent Router", version="1.0")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
BACKEND = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000")
BACKEND_BEARER = os.getenv("BACKEND_BEARER")  # optionaler Fallback
VANNA = os.getenv("VANNA_BASE_URL", "http://127.0.0.1:8080")

class ChatIn(BaseModel):
    text: str
    confirm: Optional[bool] = False

class IntentOut(BaseModel):
    intent: Literal["QUERY","ACTION_RECEIVE","ACTION_MOVE","HELP","SMALL_TALK"]
    params: dict
    confirmation_needed: bool = False
    result: Optional[dict] = None

SYSTEM = """Du bist ein Lager-Assistent. Erkenne Intents und Parameter.
Intents:
- QUERY: reine Datenabfrage (Bestand, Bins, Reorder, Ledger)
- ACTION_RECEIVE: Wareneingang (sku, qty, bin, ref_id optional)
- ACTION_MOVE: Umlagerung (sku, qty, from_bin, to_bin, ref_id optional)
- HELP/SMALL_TALK: kurze Hilfe/Antwort
Gib AUSSCHLIESSLICH JSON mit Feldern: intent, params zurück.
"""

def parse_intent(text: str) -> IntentOut:
    prompt = f"""
Text: {text}

Beispiele:
{{"intent":"QUERY","params":{{"question":"Bestand je Bin für SKU M4-12"}}}}
{{"intent":"ACTION_RECEIVE","params":{{"sku":"M4-12","qty":50,"bin":"A-01-01","ref_id":"PO-123"}}}}
{{"intent":"ACTION_MOVE","params":{{"sku":"M4-12","qty":10,"from_bin":"A-01-01","to_bin":"A-01-02","ref_id":"MOVE-7"}}}}
{{"intent":"HELP","params":{{}}}}
"""
    r = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],
        response_format={"type":"json_object"},
    )
    data = json.loads(r.choices[0].message.content)
    return IntentOut(intent=data["intent"], params=data.get("params", {}))


def build_auth_headers(authorization: str | None) -> dict:
    # 1) bevorzugt: durchgereichter Header vom Client (z.B. Frontend)
    if authorization and authorization.strip():
        return {"Authorization": authorization}
    # 2) Fallback: Service-Token aus .env
    if BACKEND_BEARER:
        return {"Authorization": BACKEND_BEARER}
    return {}


@app.post("/chat", response_model=IntentOut)
def chat(inp: ChatIn, authorization: Optional[str] = Header(None)):
    # TODO: JWT prüfen, falls nötig -> authorization
    parsed = parse_intent(inp.text)
    headers = build_auth_headers(authorization)
    if parsed.intent == "QUERY":
        q = parsed.params.get("question") or inp.text
        resp = requests.post(f"{VANNA}/ask", json={"question": q}, timeout=30)
        if resp.status_code != 200:
            raise HTTPException(400, f"Vanna-Fehler: {resp.text}")
        parsed.result = resp.json()
        return parsed

    if parsed.intent in ("ACTION_RECEIVE","ACTION_MOVE") and not inp.confirm:
        parsed.confirmation_needed = True
        return parsed

    if parsed.intent == "ACTION_RECEIVE":
        req = {k: parsed.params.get(k) for k in ["sku","qty","bin","ref_id"]}
        if not all([req.get("sku"), req.get("qty"), req.get("bin")]):
            raise HTTPException(400, "sku, qty, bin sind Pflicht")
        r = requests.post(f"{BACKEND}/api/stock/receive", json=req, headers=headers, timeout=30)
        if r.status_code != 200:
            raise HTTPException(400, f"Backend-Fehler: {r.text}")
        parsed.result = r.json()
        return parsed

    if parsed.intent == "ACTION_MOVE":
        req = {k: parsed.params.get(k) for k in ["sku","qty","from_bin","to_bin","ref_id"]}
        if not all([req.get("sku"), req.get("qty"), req.get("from_bin"), req.get("to_bin")]):
            raise HTTPException(400, "sku, qty, from_bin, to_bin sind Pflicht")
        r = requests.post(f"{BACKEND}/api/stock/move", json=req, headers=headers, timeout=30)
        if r.status_code != 200:
            raise HTTPException(400, f"Backend-Fehler: {r.text}")
        parsed.result = r.json()
        return parsed

    if parsed.intent in ("HELP","SMALL_TALK"):
        parsed.result = {"message":"Beispiele: 'Bestand je Bin für M4-12' • 'Buche +20 M4-12 nach A-01-01'."}
        return parsed

    raise HTTPException(400, "Unbekannter Intent")
