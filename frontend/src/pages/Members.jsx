import { useEffect, useState } from "react";
import { useAuth } from "../auth";
import { api } from "../api";

export default function Members() {
  const { me } = useAuth();
  const [members, setMembers] = useState([]);
  const [invites, setInvites] = useState([]);
  const [error, setError] = useState("");

  async function load() {
    try {
      setMembers(await api.get("/api/members"));
      setInvites(await api.get("/api/invites"));
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => { load(); }, []);

  async function changeRole(m, role) {
    setError("");
    try {
      await api.patch(`/api/members/${m.user_id}`, { role });
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function remove(m) {
    if (!window.confirm(`Remove ${m.username} from the company?`)) return;
    setError("");
    try {
      await api.delete(`/api/members/${m.user_id}`);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function newInvite() {
    setError("");
    try {
      const { code } = await api.post("/api/invites");
      await load();
      window.prompt("Share this invite code — it works once:", code);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <>
      <div className="topbar">
        <h2 style={{ margin: 0 }}>Members</h2>
        <button className="primary" onClick={newInvite}>Generate invite code</button>
      </div>
      <div className="error" role="alert">{error}</div>
      <table>
        <thead>
          <tr><th>Username</th><th>Role</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {members.map((m) => (
            <tr key={m.user_id}>
              <td>{m.username}{me?.username === m.username && <span className="muted"> (you)</span>}</td>
              <td>
                <select value={m.role} onChange={(e) => changeRole(m, e.target.value)} aria-label={`Role for ${m.username}`}>
                  <option value="admin">Admin</option>
                  <option value="user">User</option>
                </select>
              </td>
              <td>
                {me?.username !== m.username && (
                  <button className="danger" onClick={() => remove(m)}>Remove</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {invites.length > 0 && (
        <>
          <h3 style={{ marginTop: 24 }}>Open invite codes</h3>
          <div className="row">
            {invites.map((i) => <code key={i.code} className="invite-code">{i.code}</code>)}
          </div>
        </>
      )}
    </>
  );
}
