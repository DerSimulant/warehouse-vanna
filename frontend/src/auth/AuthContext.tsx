import { createContext, useContext, useEffect, useState } from "react";
import * as api from "../api/auth";

type User = {
  id: number; username: string; first_name: string; last_name: string; email: string;
};
type Ctx = {
  access?: string;
  user?: User;
  login: (u: string, p: string) => Promise<void>;
  logout: () => Promise<void>;
  authFetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
};
const C = createContext<Ctx>(null as any);
export const useAuth = () => useContext(C);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [access, setAccess] = useState<string>();
  const [refresh, setRefresh] = useState<string | undefined>(() => localStorage.getItem("refresh") || undefined);
  const [user, setUser] = useState<User>();

  const doRefresh = async () => {
    if (!refresh) return;
    try {
      const r = await api.refresh(refresh);
      setAccess(r.access);
      if (r.refresh) { setRefresh(r.refresh); localStorage.setItem("refresh", r.refresh); }
      if (!user) setUser(await api.me(r.access));
    } catch {
      setAccess(undefined); setUser(undefined);
    }
  };

  useEffect(() => {
    doRefresh();
    const id = setInterval(doRefresh, 1000 * 60 * 10);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = async (u: string, p: string) => {
    const t = await api.login(u, p);
    setAccess(t.access);
    setRefresh(t.refresh);
    localStorage.setItem("refresh", t.refresh);
    setUser(await api.me(t.access));
  };

  const logout = async () => {
    if (refresh) await api.logout(refresh);
    setAccess(undefined); setRefresh(undefined); setUser(undefined);
    localStorage.removeItem("refresh");
  };

  const authFetch: Ctx["authFetch"] = async (input, init) => {
    if (!access) throw new Error("Nicht eingeloggt");
    const headers = new Headers(init?.headers ?? {});
    headers.set("Authorization", `Bearer ${access}`);
    return fetch(input, { ...init, headers });
  };

  return <C.Provider value={{ access, user, login, logout, authFetch }}>{children}</C.Provider>;
}
