import { useState, type FormEvent } from "react";
import { ApiError } from "../api";
import { useAuth } from "../hooks";

export function Login() {
  const { signIn } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await signIn(username.trim(), password);
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 500 ? err.message.charAt(0).toUpperCase() + err.message.slice(1) + "." : "Could not reach the server. Is the API running (make dev)?");
      setPassword("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={submit}>
        <div className="login-brand">
          <img className="brand-mark" src="/trace360-icon.png" alt="" aria-hidden="true" />
          <span>
            <span className="brand-name">Trace<em>360</em></span>
            <span className="brand-sub">Mule account detection</span>
          </span>
        </div>
        <h1>Sign in</h1>
        <p className="muted small">Use the account your administrator gave you.</p>
        <label>User name
          <input type="text" autoComplete="username" autoFocus required value={username} onChange={(e) => setUsername(e.target.value)} />
        </label>
        <label>Password
          <input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <div className="login-error" role="alert">{error}</div>}
        <button type="submit" disabled={busy || !username.trim() || !password}>{busy ? "Signing in…" : "Sign in"}</button>
        <p className="muted small login-foot">Only admins see names and account numbers in full. Every sign-in is recorded.</p>
      </form>
    </div>
  );
}
