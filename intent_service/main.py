# intent_service/main.py
import os, json, re, logging, traceback, requests
from typing import Optional, Literal, List
from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# -----------------------------------------------------------------------------
# FastAPI
# -----------------------------------------------------------------------------
app = FastAPI(title="Warehouse Intent Router", version="2.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "https://lager.popken-eeg.de"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

log = logging.getLogger("intent")
log.setLevel(logging.INFO)

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY")
BACKEND         = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000")
VANNA           = os.getenv("VANNA_BASE_URL", "http://127.0.0.1:8080")

BACKEND_BEARER  = os.getenv("BACKEND_BEARER")          # optional
REFRESH_TOKEN   = os.getenv("BACKEND_REFRESH_TOKEN")
ACCESS_TOKEN    = os.getenv("BACKEND_ACCESS_TOKEN")

client = OpenAI(api_key=OPENAI_API_KEY)

ALLOWED_INTENTS = {"QUERY","ACTION_RECEIVE","ACTION_MOVE","ACTION_ISSUE","HELP","SMALL_TALK"}

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
class ChatIn(BaseModel):
    text: str
    confirm: Optional[bool] = False

class IntentOut(BaseModel):
    intent: Literal["QUERY","ACTION_RECEIVE","ACTION_MOVE","ACTION_ISSUE","HELP","SMALL_TALK"]
    params: dict
    confirmation_needed: bool = False

# -----------------------------------------------------------------------------
# HTTP helpers
# -----------------------------------------------------------------------------

def _ensure_trailing_slash(path: str) -> str:
    return path if path.endswith("/") else path + "/"

def backend_post(path: str, payload: dict, authorization: Optional[str]) -> requests.Response:
    path = _ensure_trailing_slash(path)
    url = f"{BACKEND}{path}"
    headers = {"Content-Type": "application/json", **build_auth_headers(authorization)}
    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    if resp.status_code == 401 and _refresh_token():
        headers = {"Content-Type": "application/json", **build_auth_headers(None)}
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
    return resp


def http_fail(msg: str, status: int = 500):
    return {"speech_text": msg, "data": {"status": "error", "http_status": status}}

def build_auth_headers(authorization: Optional[str] = None) -> dict:
    if authorization and authorization.strip():
        return {"Authorization": authorization.strip()}
    if ACCESS_TOKEN:
        return {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    if BACKEND_BEARER:
        return {"Authorization": BACKEND_BEARER}
    return {}

def _refresh_token() -> bool:
    global ACCESS_TOKEN
    if not REFRESH_TOKEN:
        return False
    r = requests.post(f"{BACKEND}/api/auth/refresh/", json={"refresh": REFRESH_TOKEN}, timeout=10)
    if r.ok:
        ACCESS_TOKEN = r.json().get("access")
        return bool(ACCESS_TOKEN)
    return False

def backend_get(path: str, params: dict, authorization: Optional[str]) -> requests.Response:
    path = _ensure_trailing_slash(path)
    url = f"{BACKEND}{path}"
    headers = {"Accept": "application/json", **build_auth_headers(authorization)}
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    if resp.status_code == 401 and _refresh_token():
        headers = {"Accept": "application/json", **build_auth_headers(None)}
        resp = requests.get(url, params=params, headers=headers, timeout=30)
    return resp

def backend_get_resilient(paths: List[str], params: dict, authorization: Optional[str]) -> requests.Response:
    """
    Probiert mehrere Pfade (z. B. mit/ohne Slash) der Reihe nach.
    """
    last = None
    for p in paths:
        r = backend_get(p, params, authorization)
        if r.ok:
            return r
        last = r
    return last

def backend_post_resilient(paths: List[str], payload: dict, authorization: Optional[str]) -> requests.Response:
    last = None
    for p in paths:
        r = backend_post(p, payload, authorization)
        if r.ok:
            return r
        last = r
    return last

def _extract_backend_error(resp: Optional[requests.Response]) -> tuple[str, str]:
    if resp is None:
        return ("BACKEND_UNREACHABLE", "Backend nicht erreichbar.")
    try:
        data = resp.json()
        msg = data.get("speech_text") or data.get("detail") or data.get("error") or resp.text
    except Exception:
        msg = resp.text or ""
    msg_low = (msg or "").lower()

    if resp.status_code == 404 and "bin" in msg_low and "nicht gefunden" in msg_low:
        if "from_bin" in msg_low or "von" in msg_low:
            return ("BIN_FROM_NOT_FOUND", msg)
        if "to_bin" in msg_low or "nach-bin" in msg_low or "nach " in msg_low:
            return ("BIN_TO_NOT_FOUND", msg)
        return ("BIN_NOT_FOUND", msg)

    if "insufficient stock" in msg_low or "nicht genug bestand" in msg_low:
        return ("INSUFFICIENT_STOCK", msg)

    if resp.status_code == 401: return ("UNAUTHORIZED", msg or "Nicht autorisiert.")
    if resp.status_code == 400: return ("BAD_REQUEST",   msg or "Ungültige Eingabe.")
    if resp.status_code == 404: return ("NOT_FOUND",     msg or "Nicht gefunden.")
    if resp.status_code >= 500: return ("BACKEND_ERROR", msg or "Serverfehler im Backend.")
    return ("UNKNOWN_ERROR", msg or "Unbekannter Fehler")

def backend_error_response(resp: Optional[requests.Response], endpoint: str, status_fallback: int = 500):
    code, msg = _extract_backend_error(resp)
    status_code = resp.status_code if (resp is not None and resp.status_code) else status_fallback
    return {
        "speech_text": msg or "Fehler.",
        "data": {
            "status": "error",
            "http_status": status_code,
            "error_code": code,
            "endpoint": endpoint,
        },
    }

# -----------------------------------------------------------------------------
# Normalisierung & Fallbacks
# -----------------------------------------------------------------------------
def fallback_kind_and_sku(text: str):
    t = text.lower()
    kind = None
    if "bewegung" in t or "moves" in t or "history" in t:
        kind = "moves"
    elif "reorder" in t or "meldung" in t:
        kind = "reorder"
    elif "bestand" in t or "wie viel" in t or "wieviel" in t or "wo liegt" in t:
        kind = "stock"
    m = re.search(r"([A-Z0-9]+[-_x][A-Z0-9]+)", text, re.I)  # M4-12, M4x12, ABC-100
    return kind, (m.group(1) if m else None)

def clean_bin_text(s: Optional[str]) -> Optional[str]:
    if not s: return s
    t = re.sub(r'^\s*bin\s+', '', s, flags=re.I)
    t = re.sub(r'[\s_]+', '-', t)
    t = re.sub(r'-{2,}', '-', t)
    return t.strip()

def resolve_best_sku(q: str, authorization: Optional[str]) -> Optional[str]:
    """
    Nutzt /api/resolve-item/ und liefert beste SKU (Score >= 0.85), sonst None.
    Resilient gegen Slash-Inkonsistenzen.
    """
    try:
        rr = backend_get_resilient(
            ["/api/resolve-item/"],
            {"q": q},
            authorization,
        )
        if not rr or not rr.ok:
            return None
        env = rr.json()
        cands = (env.get("data") or {}).get("candidates") or []
        if not cands:
            return None
        best = cands[0]
        score = float(best.get("score", 0) or 0)
        if score >= 0.85 and best.get("sku"):
            return best["sku"]
        return None
    except Exception:
        return None

def normalize_action_request(req: dict, authorization: Optional[str], fallback_text: str):
    """
    - SKU ggf. via resolve-item normalisieren
    - Bins säubern (Backend löst endgültig auf)
    """
    if not req.get("sku"):
        s = resolve_best_sku(fallback_text, authorization)
        if s: req["sku"] = s
    else:
        s = resolve_best_sku(req["sku"], authorization)
        if s: req["sku"] = s

    for key in ("bin", "from_bin", "to_bin"):
        if key in req and req[key]:
            req[key] = clean_bin_text(req[key])

# -----------------------------------------------------------------------------
# LLM Prompting
# -----------------------------------------------------------------------------
SYSTEM = """Du bist ein Lager-Assistent. Antworte AUSSCHLIESSLICH mit gültigem JSON:
{
  "intent": "QUERY | ACTION_RECEIVE | ACTION_MOVE | ACTION_ISSUE | HELP | SMALL_TALK",
  "params": { ... }
}
Regeln:
- Erkenne frei gesprochene deutsche Sätze.
- SKU IM ROHTEXT zurückgeben (M4x12, M4-12 etc.). Normalisierung macht das Backend.
- qty: Zahl oder Zahl-String ok ("5", 5, "5 Stück").
- Bin/Lagerplatz roh in bin/from_bin/to_bin (z. B. "A01-01", "MAIN-A-01-01", "Bin A 01 01").
- Wenn unsicher → intent = HELP.
"""

FEW_SHOT = """Beispiele:

Text: "Bestand je Bin für SKU M4-12"
{"intent":"QUERY","params":{"kind":"stock","sku":"M4-12"}}

Text: "Bestand ABC Teile?"
{"intent":"QUERY","params":{"kind":"stock","query":"ABC Teile"}}

Text: "Zeig Bewegungen von ABC-100, die letzten 5"
{"intent":"QUERY","params":{"kind":"moves","sku":"ABC-100","limit":5}}

Text: "Reorder Vorschläge"
{"intent":"QUERY","params":{"kind":"reorder"}}

Text: "Buche 12 Stück M4-12 in MAIN-A-01-01"
{"intent":"ACTION_RECEIVE","params":{"sku":"M4-12","qty":12,"bin":"MAIN-A-01-01"}}

Text: "Entnehme 5 M4x12 aus Bin A01-01"
{"intent":"ACTION_ISSUE","params":{"sku":"M4x12","qty":5,"from_bin":"A01-01"}}

Text: "Verschiebe 10 M4-12 von A-01-01 nach A-01-02"
{"intent":"ACTION_MOVE","params":{"sku":"M4-12","qty":10,"from_bin":"A-01-01","to_bin":"A-01-02"}}
"""

def parse_with_llm(user_text: str) -> IntentOut:
    prompt = f"{FEW_SHOT}\n\nText: {user_text}\nAntworte NUR als JSON."
    r = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.2,
        top_p=0.9,
        messages=[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],
        response_format={"type":"json_object"},
    )
    data = json.loads(r.choices[0].message.content)
    intent = data.get("intent")
    params = data.get("params", {}) or {}

    if intent not in ALLOWED_INTENTS:
        strict = ("Nur diese Intents sind erlaubt: QUERY, ACTION_RECEIVE, ACTION_MOVE, ACTION_ISSUE, HELP, SMALL_TALK. "
                  "Gib ausschließlich JSON zurück.\nText: " + user_text)
        r2 = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0.1,
            messages=[{"role":"system","content":SYSTEM},{"role":"user","content":strict}],
            response_format={"type":"json_object"},
        )
        data = json.loads(r2.choices[0].message.content)
        intent = data.get("intent")
        params = data.get("params", {}) or {}

    if intent not in ALLOWED_INTENTS:
        kind, sku = fallback_kind_and_sku(user_text)
        if kind:
            p = {"kind": kind}
            if sku: p["sku"] = sku
            return IntentOut(intent="QUERY", params=p)
        return IntentOut(intent="HELP", params={})

    return IntentOut(intent=intent, params=params)

# -----------------------------------------------------------------------------
# API
# -----------------------------------------------------------------------------
@app.post("/chat")
def chat(inp: ChatIn, authorization: Optional[str] = Header(None)):
    try:
        parsed = parse_with_llm(inp.text)

        # ------------------ QUERY ------------------
        if parsed.intent == "QUERY":
            kind  = parsed.params.get("kind")
            sku   = parsed.params.get("sku")
            limit = parsed.params.get("limit", 5)

            if not kind:
                fk, fs = fallback_kind_and_sku(inp.text)
                kind = kind or fk
                sku  = sku or fs

            # STOCK
            if kind == "stock":
                if sku:
                    r = backend_get_resilient(
                        ["/api/stock/"],
                        {"sku": sku},
                        authorization,
                    )
                    if not r or not r.ok:
                        return backend_error_response(r, "/api/stock/")
                    return r.json()

                free_q = parsed.params.get("query") or inp.text
                rr = backend_get_resilient(
                    ["/api/resolve-item/"],
                    {"q": free_q},
                    authorization,
                )
                if rr and rr.ok:
                    env = rr.json()
                    cands = (env.get("data") or {}).get("candidates") or []
                    if cands:
                        best = cands[0]
                        try:
                            score = float(best.get("score", 0) or 0)
                        except Exception:
                            score = 0.0
                        if score >= 0.85 and best.get("sku"):
                            rs = backend_get_resilient(
                                ["/api/stock/"],
                                {"sku": best["sku"]},
                                authorization,
                            )
                            if rs and rs.ok:
                                return rs.json()
                    return env
                return http_fail("Item-Suche fehlgeschlagen.", rr.status_code if rr else 502)

            # MOVES
            if kind == "moves" and sku:
                r = backend_get_resilient(
                    ["/api/stock-moves/"],
                    {"sku": sku, "limit": limit},
                    authorization,
                )
                if not r or not r.ok:
                    return backend_error_response(r, "/api/stock-moves/")
                return r.json()

            # REORDER
            if kind == "reorder":
                r = backend_get_resilient(
                    ["/api/reorder/suggestions/"],
                    {},
                    authorization,
                )
                if not r or not r.ok:
                    return backend_error_response(r, "/api/reorder/suggestions/")
                items = r.json()
                return {"speech_text": f"{len(items)} Vorschläge.", "data": {"rows": items}}

            # generische Analyse → Vanna
            q = parsed.params.get("question") or inp.text
            v = requests.post(f"{VANNA}/ask", json={"question": q}, timeout=30)
            if v.status_code != 200:
                return http_fail(f"Vanna-Fehler: {v.text}", 400)
            vdata = v.json()
            n = len(vdata.get("rows") or [])
            return {"speech_text": f"Deine Auswertung ist fertig. {n} Zeilen gefunden.", "data": vdata}

        # ------------------ ACTIONS ------------------
        if parsed.intent in ("ACTION_RECEIVE","ACTION_MOVE","ACTION_ISSUE") and not inp.confirm:
            return {
                "speech_text": "Aktion erfordert Bestätigung. Bitte 'Confirm' aktivieren.",
                "data": {"confirmation_needed": True, "intent": parsed.intent, "params": parsed.params},
            }

        # RECEIVE
        if parsed.intent == "ACTION_RECEIVE":
            req = {k: parsed.params.get(k) for k in ["sku","qty","bin","ref_id"]}
            normalize_action_request(req, authorization, fallback_text=inp.text)
            if not all([req.get("sku"), req.get("qty"), req.get("bin")]):
                return {"speech_text": "sku, qty, bin sind Pflicht", "data": {"status":"error"}}
            r = backend_post_resilient(
                ["/api/stock/receive/"],
                req,
                authorization,
            )
            if not r or not r.ok:
                return backend_error_response(r, "/api/stock/receive/")
            return r.json()

        # MOVE
        if parsed.intent == "ACTION_MOVE":
            req = {k: parsed.params.get(k) for k in ["sku","qty","from_bin","to_bin","ref_id"]}
            normalize_action_request(req, authorization, fallback_text=inp.text)
            if not all([req.get("sku"), req.get("qty"), req.get("from_bin"), req.get("to_bin")]):
                return {"speech_text": "sku, qty, from_bin, to_bin sind Pflicht", "data": {"status":"error"}}
            r = backend_post_resilient(
                ["/api/stock/move/"],
                req,
                authorization,
            )
            if not r or not r.ok:
                 return backend_error_response(r, "/api/stock/move/")
            return r.json()

        # ISSUE
        if parsed.intent == "ACTION_ISSUE":
            req = {k: parsed.params.get(k) for k in ["sku","qty","from_bin","ref_id"]}
            normalize_action_request(req, authorization, fallback_text=inp.text)

            if not req.get("from_bin") and req.get("sku"):
                stock_resp = backend_get_resilient(
                    ["/api/stock/"],
                    {"sku": req["sku"]},
                    authorization,
                )
                if stock_resp and stock_resp.ok:
                    bins = (stock_resp.json().get("data") or {}).get("bins") or []
                    if len(bins) == 1:
                        req["from_bin"] = bins[0]["bin"]
                    elif len(bins) > 1:
                        return {"speech_text": "Mehrere Bins gefunden, bitte Lagerplatz angeben.", "data": {"bins": bins}}

            if not all([req.get("sku"), req.get("qty"), req.get("from_bin")]):
                return {"speech_text": "sku, qty, from_bin sind Pflicht", "data": {"status":"error"}}

            r = backend_post_resilient(
                ["/api/stock/issue/"],
                req,
                authorization,
            )
            if not r or not r.ok:
                return backend_error_response(r, "/api/stock/issue/")
            return r.json()

        # HELP / SMALL_TALK / Default
        return {
            "speech_text": "Du musst lernen Dich besser auszudrücken. Wenn Du so einen Mist fragst, kann Dich niemand verstehen. Ich kann helfen mit: Bestand („Bestand M4-12“), Bewegungen, Wareneingang, Umlagerung, Entnahme.",
            "data": {},
        }

    except Exception as e:
        log.error("Intent /chat failed: %s\n%s", e, traceback.format_exc())
        return http_fail("Unerwarteter Fehler im Intent-Service. Siehe Server-Log.", 500)
