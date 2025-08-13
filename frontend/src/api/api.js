// Hilfsfunktion: hängt genau einen Slash ans Ende einer Basis-URL
function ensureTrailingSlash(url) {
  if (!url) return url;
  return url.endsWith("/") ? url : url + "/";
}

// Basis-URL aus .env (z.B. http://127.0.0.1:8000/api)
const API_BASE = ensureTrailingSlash(import.meta.env.VITE_API_URL);

// Beispiel-Endpunkte (nur falls du direkt ans Django-API willst)
export const MOVE_URL    = API_BASE + "stock/move/";
export const ISSUE_URL   = API_BASE + "stock/issue/";
export const RECEIVE_URL = API_BASE + "stock/receive/";
export const RESOLVE_URL = API_BASE + "resolve-item/";

// WICHTIG: den Intent lässt du wie er ist (das ist bereits ein *voller* Endpoint):
const INTENT = import.meta.env.VITE_INTENT_URL ?? "http://127.0.0.1:9000/chat";
