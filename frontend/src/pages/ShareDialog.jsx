import { useEffect, useState } from "react";
import { api } from "../api";

export default function ShareDialog({ node, onClose, onChanged }) {
  const [grants, setGrants] = useState([]);
  const [members, setMembers] = useState([]);
  const [username, setUsername] = useState("");
  const [role, setRole] = useState("viewer");
  const [error, setError] = useState("");

  useEffect(() => {
    api.get(`/api/nodes/${node.kind}/${node.id}/grants`)
      .then(setGrants)
      .catch((e) => setError(e.message));
    api.get("/api/members")
      .then(setMembers)
      .catch(() => setMembers([])); // share dialog still works if member list is hidden
  }, [node.kind, node.id]);

  async function grant(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/api/grants", { kind: node.kind, node_id: node.id, username, role });
      setGrants(await api.get(`/api/nodes/${node.kind}/${node.id}/grants`));
      setUsername("");
      onChanged?.();
    } catch (err) {
      setError(err.message);
    }
  }

  async function revoke(g) {
    setError("");
    try {
      await api.delete(`/api/grants/${g.id}`);
      setGrants((gs) => gs.filter((x) => x.id !== g.id));
      onChanged?.();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()} role="dialog" aria-label={`Share ${node.name}`}>
        <h3>Share “{node.name}”</h3>
        <div className="stack">
          {grants.length === 0 && <div className="muted">No one else has access.</div>}
          {grants.map((g) => (
            <div className="row" key={g.id}>
              <span style={{ flex: 1 }}>{g.username}</span>
              <span className="muted">{g.role}</span>
              <button className="danger" onClick={() => revoke(g)}>Revoke</button>
            </div>
          ))}
          <form onSubmit={grant} className="stack" style={{ borderTop: "1px solid var(--border)", paddingTop: 12 }}>
            <div className="row">
              <select value={username} onChange={(e) => setUsername(e.target.value)} required aria-label="Member">
                <option value="" disabled>Pick a member…</option>
                {members
                  .filter((m) => !grants.some((g) => g.username === m.username))
                  .map((m) => <option key={m.user_id} value={m.username}>{m.username}</option>)}
              </select>
              <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Role">
                <option value="viewer">Viewer</option>
                <option value="editor">Editor</option>
              </select>
              <button className="primary" type="submit">Grant</button>
            </div>
            <div className="muted">Viewer can read and download. Editor can also write, delete, and share.</div>
          </form>
          <div className="error" role="alert">{error}</div>
          <div className="row">
            <button onClick={onClose}>Close</button>
          </div>
        </div>
      </div>
    </div>
  );
}
