import { useEffect, useState } from "react";
import { api } from "../api";

const ACTION_LABELS = {
  "file.delete": "Deleted file",
  "grant.create": "Granted access",
  "grant.revoke": "Revoked access",
  "role.change": "Changed member role",
  "member.add": "Added member",
  "member.remove": "Removed member",
  "workspace.create": "Created workspace",
  "workspace.update": "Updated workspace",
};

function describe(e) {
  const m = e.metadata ?? {};
  switch (e.action) {
    case "file.delete": return `${m.file_name ?? ""}`;
    case "grant.create": return `${m.role ?? ""} → ${m.username ?? ""}`;
    case "grant.revoke": return `${m.role ?? ""} ✕ ${m.username ?? ""}`;
    case "role.change": return `${m.username ?? ""}: ${m.old_role ?? "?"} → ${m.new_role ?? "?"}`;
    case "member.add": return `${m.username ?? ""} joined as ${m.role ?? ""}`;
    case "member.remove": return `${m.username ?? ""}`;
    case "workspace.create": return `${m.workspace_name ?? ""}`;
    case "workspace.update": return `${m.workspace_name ?? ""}: default role → ${m.new_default_role || "private"}`;
    default: return JSON.stringify(m);
  }
}

export default function Audit() {
  const [entries, setEntries] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/api/audit").then(setEntries).catch((e) => setError(e.message));
  }, []);

  return (
    <>
      <div className="topbar">
        <h2 style={{ margin: 0 }}>Audit log</h2>
        <span className="muted">RBAC-affecting actions, most recent first</span>
      </div>
      <div className="error" role="alert">{error}</div>
      <table>
        <thead>
          <tr><th>When</th><th>Actor</th><th>Action</th><th>Detail</th></tr>
        </thead>
        <tbody>
          {entries.map((e) => (
            <tr key={e.id}>
              <td className="muted">{new Date(e.created_at).toLocaleString()}</td>
              <td>{e.actor ?? "—"}</td>
              <td>{ACTION_LABELS[e.action] ?? e.action}</td>
              <td>{describe(e)}</td>
            </tr>
          ))}
          {!entries.length && (
            <tr><td colSpan={4} className="muted" style={{ textAlign: "center", padding: 24 }}>No entries yet.</td></tr>
          )}
        </tbody>
      </table>
    </>
  );
}
