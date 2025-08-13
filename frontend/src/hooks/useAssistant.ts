// src/hooks/useAssistant.ts
import { api } from "../api/client";
import { speak } from "../lib/tts";

export type AssistantResult =
  | { type: "stock"; table: any; speech: string }
  | { type: "moves"; rows: any[]; speech: string }
  | { type: "resolve"; candidates: { sku: string; name: string; score: number }[]; speech: string };

function extractSkuOrQuery(input: string) {
  const txt = input.trim();

  // "bewegungen für ABC-100"
  const mMoves = txt.match(/bewegungen?\s+(?:für\s+)?([A-Za-z0-9\-_]+)/i);
  if (mMoves) return { intent: "moves" as const, value: mMoves[1] };

  // "bestand abc-100" / "stock abc-100"
  const mStock = txt.match(/(?:bestand|stock)\s+(?:von|für)?\s*([A-Za-z0-9\-_]+)/i);
  if (mStock) return { intent: "stock" as const, value: mStock[1] };

  // Fallback: komplette Query semantisch auflösen
  return { intent: "resolve" as const, value: txt };
}

export function useAssistant() {
  async function handle(text: string): Promise<AssistantResult> {
    const { intent, value } = extractSkuOrQuery(text);

    if (intent === "moves") {
      const r = await api.stockMoves(value, 5);
      speak(r.speech_text);
      return { type: "moves", rows: r.data.rows, speech: r.speech_text };
    }

    if (intent === "stock") {
      const r = await api.stock(value);
      speak(r.speech_text);
      return { type: "stock", table: r.data, speech: r.speech_text };
    }

    // resolve: unscharfe Suche → ggf. Nachfrage
    const r = await api.resolveItem(value);
    speak(r.speech_text);
    return { type: "resolve", candidates: r.data.candidates, speech: r.speech_text };
  }

  return { handle };
}
