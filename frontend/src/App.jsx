import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { useAuth } from "./auth";
import Login from "./pages/Login";
import Drive from "./pages/Drive";
import Workspaces from "./pages/Workspaces";
import Members from "./pages/Members";
import Audit from "./pages/Audit";

function Layout({ children }) {
  const { me, isAdmin, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <div className="layout">
      <nav className="sidebar" aria-label="Main navigation">
        <div className="section">{me?.company?.name ?? "Drive"}</div>
        <NavLink to="/" end className={({ isActive }) => (isActive ? "active" : "")}>
          My Drive
        </NavLink>
        {isAdmin && (
          <>
            <div className="section">Admin</div>
            <NavLink to="/workspaces" className={({ isActive }) => (isActive ? "active" : "")}>
              Workspaces
            </NavLink>
            <NavLink to="/members" className={({ isActive }) => (isActive ? "active" : "")}>
              Members
            </NavLink>
            <NavLink to="/audit" className={({ isActive }) => (isActive ? "active" : "")}>
              Audit
            </NavLink>
          </>
        )}
        <div className="spacer" />
        <div className="row" style={{ padding: "0 10px" }}>
          <span className="muted">{me?.username}</span>
          <button
            onClick={async () => {
              await logout();
              navigate("/login");
            }}
          >
            Log out
          </button>
        </div>
      </nav>
      <main className="main">{children}</main>
    </div>
  );
}

export default function App() {
  const { me, loading } = useAuth();
  if (loading) return <div style={{ padding: 40 }}>Loading…</div>;

  return (
    <Routes>
      <Route path="/login" element={me ? <Navigate to="/" replace /> : <Login />} />
      <Route
        path="/"
        element={me ? <Layout><Drive /></Layout> : <Navigate to="/login" replace />}
      />
      <Route
        path="/workspaces"
        element={me ? <Layout><Workspaces /></Layout> : <Navigate to="/login" replace />}
      />
      <Route
        path="/members"
        element={me ? <Layout><Members /></Layout> : <Navigate to="/login" replace />}
      />
      <Route
        path="/audit"
        element={me ? <Layout><Audit /></Layout> : <Navigate to="/login" replace />}
      />
    </Routes>
  );
}
