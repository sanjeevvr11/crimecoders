import { useState, type FormEvent } from "react";
import { api } from "../api";
import type { User, UserRole, UserUpdate } from "../api";
import { Async, num } from "../components";
import { useAudit, useAuth, useUsers } from "../hooks";

const ROLES: { role: UserRole; label: string; can: string }[] = [
  { role: "viewer", label: "Viewer", can: "reads every screen, data masked" },
  { role: "investigator", label: "Investigator", can: "also transactions, connections and evidence PDFs, data masked" },
  { role: "admin", label: "Admin", can: "everything, data unmasked, Ingestion, users and this log" },
];

const ACTIONS: Record<string, string> = {
  login: "Signed in", login_failed: "Failed sign-in", logout: "Signed out",
  view_account: "Opened account", view_transactions: "Viewed transactions", view_connections: "Viewed connections",
  download_report: "Downloaded PDF", run_pipeline: "Re-ran analysis",
  data_upload: "Uploaded statement", data_remove: "Removed statement", data_run: "Ran analysis on data", data_restore: "Restored data",
  user_create: "Added user", user_update: "Changed user",
};

/** actions that show account data, so masked / unmasked matters */
const SEES_DATA = new Set(["view_account", "view_transactions", "view_connections", "download_report"]);

const AUDIT_PAGE = 50;

const when = (ts: string | null | undefined) => (ts ? new Date(ts).toLocaleString() : "never");

/** 14 characters, no look-alikes (0/O, 1/l/I), from the browser's secure random source. */
function newPassword(): string {
  const chars = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  return Array.from(crypto.getRandomValues(new Uint32Array(14)), (n) => chars[n % chars.length]).join("");
}

export function Users() {
  const { me } = useAuth();
  const users = useUsers();
  const [note, setNote] = useState<{ ok: boolean; text: string }>();
  const [resetFor, setResetFor] = useState<number>();
  const [resetPw, setResetPw] = useState("");

  const [form, setForm] = useState({ username: "", display_name: "", role: "viewer" as UserRole, password: "" });
  const [busy, setBusy] = useState(false);

  const [auditUser, setAuditUser] = useState("");
  const [auditAction, setAuditAction] = useState("");
  const [offset, setOffset] = useState(0);
  const audit = useAudit(AUDIT_PAGE, offset, auditUser || undefined, auditAction || undefined);

  const run = async (what: () => Promise<unknown>, done: string) => {
    setBusy(true);
    setNote(undefined);
    try {
      await what();
      setNote({ ok: true, text: done });
      users.reload();
      audit.reload();
      return true;
    } catch (e) {
      setNote({ ok: false, text: (e as Error).message });
      return false;
    } finally {
      setBusy(false);
    }
  };

  const add = async (e: FormEvent) => {
    e.preventDefault();
    const body = { ...form, username: form.username.trim(), display_name: form.display_name.trim() || null };
    if (await run(() => api.createUser(body), `Added ${body.username}. Give them the password: ${form.password}`))
      setForm({ username: "", display_name: "", role: "viewer", password: "" });
  };
  const update = (u: User, body: UserUpdate, done: string) => run(() => api.updateUser(u.id, body), done);
  const saveReset = async (u: User) => {
    if (await update(u, { password: resetPw }, `New password for ${u.username}: ${resetPw}. Their open sessions were signed out.`)) {
      setResetFor(undefined);
      setResetPw("");
    }
  };

  return (
    <div>
      <h1>Users</h1>
      <p className="muted">Who can sign in to Trace360 and what they can see. Changing someone's role, deactivating them or resetting their password signs them out everywhere.</p>

      <div className="role-legend">
        {ROLES.map((r) => <div key={r.role}><span className={`role-chip role-${r.role}`}>{r.label}</span> {r.can}</div>)}
      </div>

      {note && <div className={note.ok ? "users-note ok" : "users-note bad"} role="status">{note.text}</div>}

      <section className="add-user">
        <h2>Add a user</h2>
        <form className="add-user-form" onSubmit={add}>
          <label>User name<input type="text" required autoComplete="off" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></label>
          <label>Full name<input type="text" autoComplete="off" placeholder="optional" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} /></label>
          <label>Role<select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as UserRole })}>
            {ROLES.map((r) => <option key={r.role} value={r.role}>{r.label}</option>)}
          </select></label>
          <label className="pw-label">Password
            <span className="pw-row">
              <input type="text" required minLength={8} autoComplete="new-password" placeholder="8+ characters" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
              <button type="button" className="ghost" onClick={() => setForm({ ...form, password: newPassword() })}>Generate</button>
            </span>
          </label>
          <button type="submit" disabled={busy}>Add user</button>
        </form>
      </section>

      <h2>Everyone who can sign in</h2>
      <Async state={users} what="users">
        {(list) => (
          <table className="users-table">
            <thead><tr><th>User</th><th>Role</th><th>Status</th><th>Last sign-in</th><th>Added</th><th /></tr></thead>
            <tbody>
              {list.map((u) => {
                const self = u.id === me?.user.id;
                return [
                  <tr key={u.id} className={u.active ? "" : "inactive"}>
                    <td><b>{u.display_name || u.username}</b>{u.display_name && <span className="muted small"> · {u.username}</span>}{self && <span className="you">you</span>}</td>
                    <td>
                      <select value={u.role} disabled={busy || self} title={self ? "You can't change your own role" : "Change role"} aria-label={`Role of ${u.username}`}
                        onChange={(e) => update(u, { role: e.target.value as UserRole }, `${u.username} is now ${e.target.value}.`)}>
                        {ROLES.map((r) => <option key={r.role} value={r.role}>{r.label}</option>)}
                      </select>
                    </td>
                    <td>{u.active ? <span className="status-on">Active</span> : <span className="status-off">Deactivated</span>}</td>
                    <td className="small">{when(u.last_login_at)}</td>
                    <td className="small">{when(u.created_at)}</td>
                    <td><div className="row-actions">
                      <button type="button" className="ghost" disabled={busy} onClick={() => { setResetFor(resetFor === u.id ? undefined : u.id); setResetPw(newPassword()); }}>Reset password</button>
                      {!self && (u.active
                        ? <button type="button" className="ghost danger" disabled={busy} onClick={() => update(u, { active: false }, `${u.username} can no longer sign in.`)}>Deactivate</button>
                        : <button type="button" className="ghost" disabled={busy} onClick={() => update(u, { active: true }, `${u.username} can sign in again.`)}>Reactivate</button>)}
                    </div></td>
                  </tr>,
                  resetFor === u.id && (
                    <tr key={`${u.id}-reset`} className="reset-row">
                      <td colSpan={6}>
                        <span className="pw-row">
                          New password for {u.username}:
                          <input type="text" minLength={8} value={resetPw} onChange={(e) => setResetPw(e.target.value)} aria-label="New password" />
                          <button type="button" className="ghost" onClick={() => setResetPw(newPassword())}>Generate</button>
                          <button type="button" disabled={busy || resetPw.length < 8} onClick={() => saveReset(u)}>Save</button>
                          <button type="button" className="ghost" onClick={() => setResetFor(undefined)}>Cancel</button>
                        </span>
                      </td>
                    </tr>
                  ),
                ];
              })}
            </tbody>
          </table>
        )}
      </Async>

      <h2>Audit log</h2>
      <p className="muted">Every sign-in, account and transaction view, PDF download, upload, analysis run and user change, newest first.</p>
      <div className="controls">
        <label>User <select value={auditUser} onChange={(e) => { setAuditUser(e.target.value); setOffset(0); }}>
          <option value="">everyone</option>
          {(users.data ?? []).map((u) => <option key={u.id} value={u.username}>{u.username}</option>)}
        </select></label>
        <label>Action <select value={auditAction} onChange={(e) => { setAuditAction(e.target.value); setOffset(0); }}>
          <option value="">all</option>
          {Object.entries(ACTIONS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select></label>
        {audit.data && <>
          <span>{audit.data.total ? `${num(offset + 1)}–${num(Math.min(offset + AUDIT_PAGE, audit.data.total))} of ${num(audit.data.total)}` : "no entries"}</span>
          <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - AUDIT_PAGE))}>Newer</button>
          <button disabled={offset + AUDIT_PAGE >= audit.data.total} onClick={() => setOffset(offset + AUDIT_PAGE)}>Older</button>
        </>}
      </div>
      <Async state={audit} what="audit log" isEmpty={(d) => d.items.length === 0} empty="Nothing recorded yet for this filter.">
        {(d) => (
          <table>
            <thead><tr><th>When</th><th>User</th><th>Action</th><th>On</th><th>Data</th><th>Detail</th><th>Address</th></tr></thead>
            <tbody>
              {d.items.map((x) => (
                <tr key={x.id} className={x.action === "login_failed" ? "audit-fail" : ""}>
                  <td className="small">{when(x.ts)}</td>
                  <td>{x.username ?? "—"}{x.role && <span className="muted small"> · {x.role}</span>}</td>
                  <td>{ACTIONS[x.action] ?? x.action}</td>
                  <td className="small mono">{x.target ?? ""}</td>
                  <td>{x.unmasked ? <span className="unmasked-tag">unmasked</span> : SEES_DATA.has(x.action) ? <span className="muted small">masked</span> : ""}</td>
                  <td className="small">{x.detail ?? ""}</td>
                  <td className="small muted mono">{x.ip ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Async>
    </div>
  );
}
