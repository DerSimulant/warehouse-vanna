import { useRef, useState } from "react";
import { useAuth } from "./auth/AuthContext";
import LogoutButton from "./components/LogoutButton";

import { PorcupineWorkerFactory } from "@picovoice/porcupine-web-en-worker";




// Intent-Service (FastAPI, Port 9000)
const INTENT    = import.meta.env.VITE_INTENT_URL ?? "http://127.0.0.1:9000/chat";
//const ACCESS_KEY_RAW = import.meta.env.VITE_PORCUPINE_ACCESS_KEY;
//const ACCESS_KEY = (ACCESS_KEY_RAW ?? "").trim();

const ACCESS_KEY = "l0+XHz9Yqc5abSvw6sTwhERaTI5UdU5lu8TKGrNsMF4rL+mqUA/W5w==".replace(/\s+/g, "").trim();

//const WAKEWORD  = (import.meta.env.VITE_WAKEWORD ?? "hey google").trim();
const WAKEWORD="Hey Google";

console.log('ENV aus Vite:', import.meta.env);
console.log('PV key present?', Boolean(ACCESS_KEY), 'len:', ACCESS_KEY.length);



export default function App() {
  const { authFetch, user } = useAuth();
  const [text, setText] = useState("Bestand je Bin für SKU M4-12?");
  const [confirm, setConfirm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [resp, setResp] = useState(null);
  const [error, setError] = useState("");
  const recRef = useRef(null);
  const [recognizing, setRecognizing] = useState(false);

  // Wake-word state/refs
  const [wakeActive, setWakeActive] = useState(false);
  const porcupineRef = useRef(null);

  // -----------------------------------------------------------
  // Wake Word starten (LAZY IMPORT, damit die App nie „weiß“ wird)
  // -----------------------------------------------------------
async function startWakeWord() {
  if (wakeActive) return;
  try {
    const worker = await PorcupineWorkerFactory.create(
      ACCESS_KEY,
      [{ builtin: "Hey Google" }],      // ⬅️ gültiges Built-in
      { sensitivities: [0.6] }
    );
    porcupineRef.current = worker;
    worker.onmessage = (e) => {
      if (e.data?.keywordLabel) startVoice();
      if (e.data?.error) { setError(String(e.data.error)); stopWakeWord(); }
    };
    setWakeActive(true);
  } catch (err) {
    console.error("Wake Word init fehlgeschlagen:", err);
    setError(`Wake Word konnte nicht gestartet werden: ${err?.message ?? String(err)}`);
  }
}




  function stopWakeWord() {
    try {
      porcupineRef.current?.postMessage({ command: "release" });
    } catch {}
    porcupineRef.current = null;
    setWakeActive(false);
  }

  // -----------------------------------------------------------
  // Dein bestehender Chat-Request bleibt unverändert
  // -----------------------------------------------------------
  async function send() {
    setLoading(true);
    setError("");
    setResp(null);

    try {
      const r = await authFetch(INTENT, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ text, confirm }),
      });

      const ctype = r.headers.get("content-type") || "";
      const body = await r.text();
      if (!ctype.includes("application/json")) {
        throw new Error(`Server liefert kein JSON (${ctype}) → ${body.slice(0, 100)}…`);
      }

      const data = JSON.parse(body);
      const isError = !r.ok || (data?.data && data.data.status === "error");
      if (isError) {
        const code = data?.data?.error_code || "UNKNOWN_ERROR";
        const msg  = data?.speech_text || data?.detail || data?.error || `${r.status} ${r.statusText}`;
        if (["BIN_NOT_FOUND", "BIN_FROM_NOT_FOUND", "BIN_TO_NOT_FOUND"].includes(code)) {
          setError(`⚠️ ${msg}\nTipp: Prüfe Schreibweise oder lege den Lagerplatz an.`);
        } else if (code === "INSUFFICIENT_STOCK") {
          setError(`⚠️ Zu wenig Bestand: ${msg}`);
        } else {
          setError(msg);
        }
        return;
      }
      setResp(data);
      speakText(data.speech_text);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }

  function speakText(s) {
    try {
      const synth = window.speechSynthesis;
      if (!synth || !s) return;
      synth.cancel();
      const u = new SpeechSynthesisUtterance(s);
      u.lang = "de-DE";
      synth.speak(u);
    } catch {}
  }

  function startVoice() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      setError("Spracherkennung wird von diesem Browser nicht unterstützt.");
      return;
    }
    const rec = new SR();
    rec.lang = "de-DE";
    rec.continuous = false;
    rec.interimResults = false;

    rec.onresult = (ev) => {
      const t = Array.from(ev.results).map(r => r[0].transcript).join(" ");
      setText(t);
      setRecognizing(false);
      // Optional: direkt absenden
      // send();
    };
    rec.onerror = (e) => {
      setError(`Voice: ${e.error}`);
      setRecognizing(false);
    };
    rec.onend = () => setRecognizing(false);

    recRef.current = rec;
    setRecognizing(true);
    rec.start();
  }

  function stopVoice() {
    recRef.current?.stop();
    setRecognizing(false);
  }

  return (
    <div className="app">
      <div className="row">
        <header className="header">
        <h1 className="header-title">Laber mit dem Lager</h1>
        <p className="header-sub">
          Hört Dir ja sonst eh keiner zu. Und macht nichts, wenn´s schnell geht! </p>
          <div className="top-right">
            <div className="user-actions">
              {user && <span className="user-pill">👤 {user.username}</span>}
              <LogoutButton />
              </div>

        <div className="badge">Intent: {INTENT}</div>
       </div>
        </header>
      </div>
        
        

      <div className="card" style={{ marginTop: 16 }}>
        <label>Frage ans Lager (Vanna + Intent). Für Aktionen (WE/Bewegung) „Confirm“ aktivieren.</label>
        <textarea value={text} onChange={(e) => setText(e.target.value)} />

        <div className="controls">
          <label>
            <input
              type="checkbox"
              checked={confirm}
              onChange={(e) => setConfirm(e.target.checked)}
              style={{ marginRight: 8 }}
            />
            Confirm ausführen
          </label>

          <button onClick={send} disabled={loading}>
            {loading ? "Sende..." : "Senden"}
          </button>

          {!recognizing ? (
            <button className="micro-btn" onClick={startVoice} title="Spracheingabe starten">🎤 Aufnahme</button>
          ) : (
            <button className="micro-btn" onClick={stopVoice} title="Stop">⏹️ Stop</button>
          )}

          {!wakeActive ? (
            <button className="micro-btn" onClick={startWakeWord} title={`Wake Word starten (${WAKEWORD})`}>
              💤 Wake Word
            </button>
          ) : (
            <button className="micro-btn" onClick={stopWakeWord} title="Wake Word stoppen">🚫 Wake Word</button>
          )}
        </div>

        {error && (
          <div className="pre" style={{ borderColor: "var(--danger)", marginTop: 12 }}>
            {error}
          </div>
        )}

        {resp && (
          <>
            <div className="kv">Antwort</div>
            <div className="pre">{resp.speech_text}</div>

            {Array.isArray(resp?.data?.bins) && resp.data.bins.length > 0 && (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>{Object.keys(resp.data.bins[0]).map((k) => <th key={k}>{k}</th>)}</tr>
                  </thead>
                  <tbody>
                    {resp.data.bins.map((r, i) => (
                      <tr key={i}>{Object.keys(resp.data.bins[0]).map((k) => <td key={k}>{String(r[k])}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {Array.isArray(resp?.data?.rows) && resp.data.rows.length > 0 && (
              <div className="table-wrap" style={{ marginTop: 12 }}>
                <table>
                  <thead>
                    <tr>{Object.keys(resp.data.rows[0]).map((k) => <th key={k}>{k}</th>)}</tr>
                  </thead>
                  <tbody>
                    {resp.data.rows.map((r, i) => (
                      <tr key={i}>{Object.keys(resp.data.rows[0]).map((k) => <td key={k}>{String(r[k])}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {Array.isArray(resp?.data?.candidates) && resp.data.candidates.length > 0 && (
              <div className="table-wrap" style={{ marginTop: 12 }}>
                <table>
                  <thead>
                    <tr>{Object.keys(resp.data.candidates[0]).map((k) => <th key={k}>{k}</th>)}</tr>
                  </thead>
                  <tbody>
                    {resp.data.candidates.map((r, i) => (
                      <tr key={i}>{Object.keys(resp.data.candidates[0]).map((k) => <td key={k}>{String(r[k])}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
