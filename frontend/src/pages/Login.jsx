import { useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { useNavigate } from "react-router-dom";

export default function Login() {
  const { login } = useAuth();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState("");
  const nav = useNavigate();

  const onSubmit = async (e) => {
    e.preventDefault(); setErr("");
    try { await login(u, p); nav("/"); }
    catch (e) { setErr(e?.message || "Login fehlgeschlagen"); }
  };

  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1 className="login-title">Willkommen zum Popken EEG Warehousemanagement</h1>
        <p className="login-sub">
          Um zu sehen, was wir alles Cooles im Lager haben und um die Buchungen
          auf Stand zu halten, loggen Sie sich bitte ein.
        </p>

        <form className="login-form" onSubmit={onSubmit}>
          <input
            className="input"
            placeholder="Benutzername"
            value={u}
            onChange={(e) => setU(e.target.value)}
          />
          <input
            className="input"
            placeholder="Passwort"
            type="password"
            value={p}
            onChange={(e) => setP(e.target.value)}
          />
          {err && <div className="error">{err}</div>}
          <div className="login-row">
            <button className="btn btn-warning btn-sm" type="submit">Login</button>
          </div>
        </form>
      </div>
    </div>
  );
}
