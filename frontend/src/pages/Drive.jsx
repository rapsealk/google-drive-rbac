import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import ShareDialog from "./ShareDialog";

function fmtSize(n) {
  if (n > 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  if (n > 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${n} B`;
}

export default function Drive() {
  const [workspaces, setWorkspaces] = useState([]);
  const [wsId, setWsId] = useState(null);
  // Breadcrumb chain of {id, name}; empty = workspace root.
  const [path, setPath] = useState([]);
  const [contents, setContents] = useState({ folders: [], files: [], workspace: null });
  const [error, setError] = useState("");
  const [sharing, setSharing] = useState(null); // {kind, id, name}
  const [newFolder, setNewFolder] = useState(false);
  const [folderName, setFolderName] = useState("");
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef(null);

  const currentFolderId = path.length ? path[path.length - 1].id : null;

  useEffect(() => {
    api.get("/api/workspaces").then((ws) => {
      setWorkspaces(ws);
      if (ws.length) setWsId((id) => id ?? ws[0].id);
    }).catch((e) => setError(e.message));
  }, []);

  const load = useCallback(async () => {
    if (!wsId) return;
    setError("");
    try {
      const data = currentFolderId
        ? await api.get(`/api/folders/${currentFolderId}`)
        : await api.get(`/api/workspaces/${wsId}/contents`);
      setContents(data);
    } catch (e) {
      setError(e.message);
    }
  }, [wsId, currentFolderId]);

  useEffect(() => { load(); }, [load]);

  async function upload(files) {
    if (!files?.length || !wsId) return;
    setUploading(true);
    setError("");
    try {
      for (const file of files) {
        const { key, upload_url } = await api.post("/api/files/presign", {
          workspace_id: wsId,
          folder_id: currentFolderId,
          name: file.name,
          size: file.size,
          content_type: file.type || "application/octet-stream",
        });
        const put = await fetch(upload_url, { method: "PUT", body: file, headers: { "Content-Type": file.type || "application/octet-stream" } });
        if (!put.ok) throw new Error(`upload failed (HTTP ${put.status})`);
        await api.post("/api/files/finalize", {
          workspace_id: wsId,
          folder_id: currentFolderId,
          name: file.name,
          key,
          size: file.size,
          content_type: file.type || "application/octet-stream",
        });
      }
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function download(file) {
    setError("");
    try {
      const { download_url } = await api.get(`/api/files/${file.id}`);
      window.open(download_url, "_blank");
    } catch (e) {
      setError(e.message);
    }
  }

  async function deleteNode(kind, id, name) {
    if (!window.confirm(`Delete "${name}"${kind === "folder" ? " and everything inside" : ""}?`)) return;
    setError("");
    try {
      await api.delete(kind === "folder" ? `/api/folders/${id}` : `/api/files/${id}`);
      if (kind === "folder" && currentFolderId === id) setPath((p) => p.slice(0, -1));
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  async function createFolder(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/api/folders", { workspace_id: wsId, parent_id: currentFolderId, name: folderName });
      setFolderName("");
      setNewFolder(false);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  const ws = contents.workspace ?? workspaces.find((w) => w.id === wsId);

  return (
    <>
      <div className="topbar">
        <h2 style={{ margin: 0 }}>My Drive</h2>
        <div className="row">
          <select
            aria-label="Workspace"
            value={wsId ?? ""}
            onChange={(e) => { setWsId(Number(e.target.value)); setPath([]); }}
          >
            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>{w.name}</option>
            ))}
          </select>
          <input type="file" multiple ref={fileInput} onChange={(e) => upload(e.target.files)} style={{ display: "none" }} />
          <button className="primary" disabled={uploading || !wsId} onClick={() => fileInput.current?.click()}>
            {uploading ? "Uploading…" : "Upload"}
          </button>
          <button onClick={() => setNewFolder(true)}>New folder</button>
        </div>
      </div>

      <div className="breadcrumb" aria-label="Breadcrumb">
        <a onClick={() => setPath([])}>{ws?.name ?? "—"}</a>
        {path.map((p, i) => (
          <span key={p.id}>
            {" / "}
            {i < path.length - 1
              ? <a onClick={() => setPath(path.slice(0, i + 1))}>{p.name}</a>
              : <strong>{p.name}</strong>}
          </span>
        ))}
      </div>

      <div className="error" role="alert">{error}</div>

      <div>
        {contents.folders.map((f) => (
          <div key={`f${f.id}`} className="file-row" role="button" tabIndex={0}
               onClick={() => setPath([...path, { id: f.id, name: f.name }])}
               onKeyDown={(e) => e.key === "Enter" && setPath([...path, { id: f.id, name: f.name }])}>
            <span aria-hidden>📁</span>
            <span className="name">{f.name}</span>
            <button aria-label={`Share ${f.name}`} onClick={(e) => { e.stopPropagation(); setSharing({ kind: "folder", id: f.id, name: f.name }); }}>Share</button>
            <button className="danger" aria-label={`Delete ${f.name}`} onClick={(e) => { e.stopPropagation(); deleteNode("folder", f.id, f.name); }}>Delete</button>
          </div>
        ))}
        {contents.files.map((f) => (
          <div key={`file${f.id}`} className="file-row" role="button" tabIndex={0}
               onClick={() => download(f)}
               onKeyDown={(e) => e.key === "Enter" && download(f)}>
            <span aria-hidden>📄</span>
            <span className="name">{f.name}</span>
            <span className="size">{fmtSize(f.size)}</span>
            <button aria-label={`Share ${f.name}`} onClick={(e) => { e.stopPropagation(); setSharing({ kind: "file", id: f.id, name: f.name }); }}>Share</button>
            <button className="danger" aria-label={`Delete ${f.name}`} onClick={(e) => { e.stopPropagation(); deleteNode("file", f.id, f.name); }}>Delete</button>
          </div>
        ))}
        {!contents.folders.length && !contents.files.length && (
          <div className="muted" style={{ padding: 24, textAlign: "center" }}>Empty — upload something.</div>
        )}
      </div>

      {sharing && (
        <ShareDialog
          node={sharing}
          onClose={() => setSharing(null)}
          onChanged={load}
        />
      )}

      {newFolder && (
        <div className="dialog-backdrop" onClick={() => setNewFolder(false)}>
          <form className="dialog" onClick={(e) => e.stopPropagation()} onSubmit={createFolder}>
            <h3>New folder</h3>
            <div className="stack">
              <input autoFocus placeholder="Folder name" value={folderName} onChange={(e) => setFolderName(e.target.value)} required />
              <div className="row">
                <button type="button" onClick={() => setNewFolder(false)}>Cancel</button>
                <button className="primary" type="submit">Create</button>
              </div>
            </div>
          </form>
        </div>
      )}
    </>
  );
}
