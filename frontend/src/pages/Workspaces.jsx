import { useEffect, useState } from "react";
import { api } from "../api";

export default function Workspaces() {
  const [workspaces, setWorkspaces] = useState([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  async function load() {
    try {
      setWorkspaces(await api.get("/api/workspaces"));
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => { load(); }, []);

  async function create(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/api/workspaces", { name });
      setName("");
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function setDefaultRole(w, default_role) {
    setError("");
    try {
      await api.patch(`/api/workspaces/${w.id}`, { default_role });
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <>
      <div className="topbar">
        <h2 style={{ margin: 0 }}>Workspaces</h2>
        <form className="row" onSubmit={create}>
          <input placeholder="New workspace name" value={name} onChange={(e) => setName(e.target.value)} required />
          <button className="primary">Create</button>
        </form>
      </div>
      <div className="error" role="alert">{error}</div>
      <table>
        <thead>
          <tr><th>Name</th><th>Default role (all company members)</th></tr>
        </thead>
        <tbody>
          {workspaces.map((w) => (
            <tr key={w.id}>
              <td>{w.name}</td>
              <td>
                <select value={w.default_role} onChange={(e) => setDefaultRole(w, e.target.value)} aria-label={`Default role for ${w.name}`}>
                  <option value="">Private</option>
                  <option value="viewer">Viewer</option>
                  <option value="editor">Editor</option>
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">
        Private = only explicit grants. Viewer = every employee can read everything here.
        Editor = every employee can read and write.
      </p>
    </>
  );
}
