import { useState } from "react";
import { useAuth } from "../auth";

export default function Login() {
  const { login, signup } = useAuth();
  const [tab, setTab] = useState("login");
  const [mode, setMode] = useState("create");
  const [form, setForm] = useState({ username: "", password: "", company_name: "", invite_code: "", email: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (tab === "login") {
        await login(form.username, form.password);
      } else {
        await signup({ mode, username: form.username, email: form.email, password: form.password,
                       company_name: form.company_name, invite_code: form.invite_code });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-card">
      <h1>Drive RBAC</h1>
      <div className="sub">Multi-tenant file sharing with hand-rolled RBAC</div>
      <div className="tabs" role="tablist">
        <button className={tab === "login" ? "active" : ""} onClick={() => setTab("login")}>Log in</button>
        <button className={tab === "signup" ? "active" : ""} onClick={() => setTab("signup")}>Sign up</button>
      </div>
      <form onSubmit={submit}>
        <input placeholder="Username" value={form.username} onChange={set("username")} required />
        {tab === "signup" && (
          <input type="email" placeholder="Email (optional)" value={form.email} onChange={set("email")} />
        )}
        <input type="password" placeholder="Password (min 8 chars)" value={form.password} onChange={set("password")} required minLength={8} />
        {tab === "signup" && (
          <div className="tabs">
            <button type="button" className={mode === "create" ? "active" : ""} onClick={() => setMode("create")}>
              Create company
            </button>
            <button type="button" className={mode === "join" ? "active" : ""} onClick={() => setMode("join")}>
              Join with code
            </button>
          </div>
        )}
        {tab === "signup" && mode === "create" && (
          <input placeholder="Company name" value={form.company_name} onChange={set("company_name")} required />
        )}
        {tab === "signup" && mode === "join" && (
          <input placeholder="Invite code" value={form.invite_code} onChange={set("invite_code")} required />
        )}
        <div className="error" role="alert">{error}</div>
        <button className="primary" disabled={busy}>
          {busy ? "…" : tab === "login" ? "Log in" : "Sign up"}
        </button>
      </form>
    </div>
  );
}
