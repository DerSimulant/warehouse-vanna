const API = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000/api";

export async function login(username: string, password: string) {
  const r = await fetch(`${API}/auth/login/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!r.ok) throw new Error("Login fehlgeschlagen");
  return r.json() as Promise<{ access: string; refresh: string }>;
}

export async function refresh(refreshToken: string) {
  const r = await fetch(`${API}/auth/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh: refreshToken }),
  });
  if (!r.ok) throw new Error("Refresh fehlgeschlagen");
  return r.json() as Promise<{ access: string; refresh?: string }>;
}

export async function me(access: string) {
  const r = await fetch(`${API}/auth/me/`, {
    headers: { Authorization: `Bearer ${access}` },
  });
  if (!r.ok) throw new Error("Profil konnte nicht geladen werden");
  return r.json();
}

export async function logout(refreshToken: string) {
  await fetch(`${API}/auth/logout/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh: refreshToken }),
  });
}
