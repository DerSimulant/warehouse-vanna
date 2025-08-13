// src/api/client.ts
const API_BASE: string =
  import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000/api";

function url(path: string) {
  // path immer mit führendem Slash übergeben, z. B. "/stock/?sku=..."
  return `${API_BASE}${path}`;
}

export type ApiEnvelope<T> = {
  speech_text: string;
  data: T;
};


async function getJSON<T>(path: string): Promise<ApiEnvelope<T>> {
  const endpoint = url(path);
  const res = await fetch(endpoint, {
    headers: { Accept: "application/json" },
    credentials: "include",
  });

  const ctype = res.headers.get("content-type") || "";
  const body = await res.text();
  let data: any = null;

  if (ctype.includes("application/json")) {
    try {
      data = JSON.parse(body);
    } catch {
      throw new Error("Ungültiges JSON vom Server.");
    }
  } else {
    // Hilfreiche Meldung bei HTML/Redirect/CORS
    throw new Error(`Server liefert kein JSON (${ctype}) → ${body.slice(0, 120)}…`);
  }

  if (!res.ok) {
    const msg = data?.speech_text || data?.error || `${res.status} ${res.statusText}`;
    throw new Error(msg);
  }

  return data as ApiEnvelope<T>;
}

// Klar definierte Calls (nutzen absolute URL via API_BASE)
export const api = {
  stock: (sku: string) =>
    getJSON<{ sku: string; name: string; on_hand: string | number; bins: { bin: string; location: string; qty: string | number }[] }>(
      `/stock/?sku=${encodeURIComponent(sku)}`
    ),

  stockMoves: (sku: string, limit = 5) =>
    getJSON<{ rows: { ts: string; qty: number; from_bin: string | null; to_bin: string | null; ref_type: string; ref_id: string }[] }>(
      `/stock-moves/?sku=${encodeURIComponent(sku)}&limit=${limit}`
    ),

  resolveItem: (q: string) =>
    getJSON<{ candidates: { sku: string; name: string; score: number }[] }>(
      `/resolve-item/?q=${encodeURIComponent(q)}`
    ),
};

export const intent = {
  chat: (text: string, confirm: boolean) =>
    fetch((import.meta as any).env?.VITE_INTENT_URL ?? "http://127.0.0.1:9000/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ text, confirm }),
    }).then(async (r) => {
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j?.speech_text || j?.detail || r.statusText);
      return j; // { speech_text, data: ... }
    }),
};
