import { createContext, useContext, useEffect, useState } from "react";
import { api } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [me, setMe] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/api/auth/me")
      .then(setMe)
      .catch(() => setMe(null))
      .finally(() => setLoading(false));
  }, []);

  const value = {
    me,
    loading,
    isAdmin: me?.role === "admin",
    async login(username, password) {
      setMe(await api.post("/api/auth/login", { username, password }));
    },
    async signup(payload) {
      setMe(await api.post("/api/auth/signup", payload));
    },
    async logout() {
      await api.post("/api/auth/logout");
      setMe(null);
    },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
