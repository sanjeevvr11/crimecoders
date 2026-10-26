import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { ApiError } from "../api";
import { ICONS, NetworkBackdrop } from "../components";
import { useAuth, usePublicSummary } from "../hooks";

const STEPS = [
  { n: "01", title: "Ingest", text: "Upload bank statements in any of the supported layouts. Each sheet is checked before it is used." },
  { n: "02", title: "Score", text: "Rule indicators, an anomaly model and network position give each account an explainable risk score." },
  { n: "03", title: "Connect", text: "Shared counterparties link accounts into a money network, so groups acting together stand out." },
  { n: "04", title: "Act", text: "Follow the money hop by hop, match victim complaints and export an evidence PDF for the case file." },
];

const FEATURES: { icon: ReactNode; title: string; text: string }[] = [
  { icon: ICONS.leads, title: "Explainable risk scores", text: "Every score lists the reasons behind it, in plain words, with points per reason." },
  { icon: ICONS.trail, title: "Money Trail", text: "Trace where money came from and where it went, across several hops." },
  { icon: ICONS.network, title: "Network analysis", text: "See accounts that deal with the same people, and who sits at the centre." },
  { icon: ICONS.complaints, title: "Complaint matching", text: "Victim reports are fuzzy-matched to the accounts and UPI ids that received money." },
  { icon: ICONS.models, title: "Unsupervised models", text: "Isolation Forest with SHAP reasons and behaviour clusters, no labels needed." },
  { icon: ICONS.users, title: "Privacy by role", text: "Data is masked by default, only admins see it in full, and every view is logged." },
];

const DEMO = [
  { role: "Admin", username: "admin", password: "Trace360-Admin" },
  { role: "Investigator", username: "investigator", password: "Trace360-Investigator" },
  { role: "Viewer", username: "viewer", password: "Trace360-Viewer" },
];

const LAST_USER = "trace360:last-user";

/** Counts from 0 up to `to` once it is on screen (instantly with reduced motion). */
function CountUp({ to }: { to: number }) {
  const [n, setN] = useState(0);
  const el = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setN(to); return; }
    let raf = 0;
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return;
      io.disconnect();
      const start = performance.now();
      const tick = (now: number) => {
        const t = Math.min(1, (now - start) / 1600);
        setN(Math.round(to * (1 - (1 - t) ** 3)));
        if (t < 1) raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    });
    if (el.current) io.observe(el.current);
    return () => { io.disconnect(); cancelAnimationFrame(raf); };
  }, [to]);
  return <span ref={el}>{n.toLocaleString("en-IN")}</span>;
}

/** Adds .in to every .reveal element below `root` as it scrolls into view. */
function useReveal(root: React.RefObject<HTMLElement>) {
  useEffect(() => {
    const els = root.current?.querySelectorAll<HTMLElement>(".reveal") ?? [];
    const io = new IntersectionObserver((entries) => entries.forEach((e) => {
      if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
    }), { threshold: 0.15 });
    els.forEach((e) => io.observe(e));
    return () => io.disconnect();
  }, [root]);
}

export function Login() {
  const { signIn } = useAuth();
  const summary = usePublicSummary();
  const page = useRef<HTMLDivElement>(null);
  const userInput = useRef<HTMLInputElement>(null);
  useReveal(page);

  const [username, setUsername] = useState(() => { try { return localStorage.getItem(LAST_USER) ?? ""; } catch { return ""; } });
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [caps, setCaps] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [shake, setShake] = useState(0);

  const submit = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!username.trim() || !password) return;
    setBusy(true);
    setError(undefined);
    try {
      await signIn(username.trim(), password);
      try { localStorage.setItem(LAST_USER, username.trim()); } catch { /* storage blocked */ }
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 500 ? err.message.charAt(0).toUpperCase() + err.message.slice(1) + "." : "Could not reach the server. Is the API running (make dev)?");
      setPassword("");
      setShake((s) => s + 1);
      setBusy(false);
    }
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => setCaps(e.getModifierState?.("CapsLock") ?? false);
  const fillDemo = (d: (typeof DEMO)[number]) => { setUsername(d.username); setPassword(d.password); setError(undefined); };
  const goToSignIn = () => {
    document.getElementById("sign-in")?.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => userInput.current?.focus({ preventScroll: true }), 350);
  };

  const jump = (id: string) => (e: React.MouseEvent) => {
    e.preventDefault();
    const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    document.getElementById(id)?.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" });
  };

  const s = summary.data?.ready ? summary.data : undefined;
  const stats = s ? [
    { n: s.n_statements, label: "statements analysed" },
    { n: s.n_transactions, label: "transactions scanned" },
    { n: s.n_counterparties, label: "counterparties mapped" },
    { n: s.n_leads, label: "high-risk leads raised" },
  ] : [];

  return (
    <div className="landing" ref={page}>
      <NetworkBackdrop />
      <div className="landing-vignette" aria-hidden="true" />

      <header className="landing-nav">
        <span className="landing-logo">
          <img className="brand-mark" src="/trace360-icon.png" alt="" aria-hidden="true" />
          <span className="brand-name">Trace<em>360</em></span>
        </span>
        <nav>
          <a href="#how" onClick={jump("how")}>How it works</a>
          <a href="#features" onClick={jump("features")}>Features</a>
          <button type="button" onClick={goToSignIn}>Sign in</button>
        </nav>
      </header>

      <section className="landing-hero">
        <div className="hero-copy">
          <span className="eyebrow rise" style={{ animationDelay: "0ms" }}><span className="live-dot" /> Mule account detection &amp; fraud investigation</span>
          <h1 className="rise" style={{ animationDelay: "120ms" }}>
            Trace the money.<br /><span className="shimmer">Find the mules.</span>
          </h1>
          <p className="hero-sub rise" style={{ animationDelay: "240ms" }}>
            Trace360 reads bank statements, scores every account with reasons you can explain, maps who moves money to whom,
            and turns it into evidence an investigator can act on.
          </p>
          <div className="hero-ctas rise" style={{ animationDelay: "360ms" }}>
            <button type="button" className="cta" onClick={goToSignIn}>Start investigating <span aria-hidden="true">→</span></button>
            <a className="cta-ghost" href="#how" onClick={jump("how")}>See how it works</a>
          </div>
          {stats.length > 0 && (
            <dl className="hero-stats rise" style={{ animationDelay: "480ms" }}>
              {stats.map((x) => (
                <div key={x.label}><dt><CountUp to={x.n} /></dt><dd>{x.label}</dd></div>
              ))}
            </dl>
          )}
        </div>

        <div className="hero-signin rise" style={{ animationDelay: "200ms" }}>
          <form id="sign-in" key={shake} className={`login-card glow-border${shake ? " shake" : ""}`} onSubmit={submit}>
            <h2>Sign in</h2>
            <p className="muted small">Welcome back. Use the account your administrator gave you.</p>
            <label>User name
              <input ref={userInput} type="text" autoComplete="username" autoFocus={!username} required value={username}
                onChange={(e) => setUsername(e.target.value)} />
            </label>
            <label>Password
              <span className="pw-field">
                <input type={showPw ? "text" : "password"} autoComplete="current-password" autoFocus={!!username} required value={password}
                  onChange={(e) => setPassword(e.target.value)} onKeyUp={onKey} onKeyDown={onKey} />
                <button type="button" className="pw-toggle" onClick={() => setShowPw((v) => !v)} aria-label={showPw ? "Hide password" : "Show password"} aria-pressed={showPw}>
                  {showPw ? "Hide" : "Show"}
                </button>
              </span>
            </label>
            {caps && <div className="caps-hint" role="status">Caps Lock is on</div>}
            {error && <div className="login-error" role="alert">{error}</div>}
            <button type="submit" className="signin-btn" disabled={busy || !username.trim() || !password}>
              {busy ? <><span className="spinner" aria-hidden="true" /> Signing in…</> : "Sign in"}
            </button>
            <div className="demo-access">
              <span className="muted small">Demo access</span>
              <div className="demo-chips">
                {DEMO.map((d) => (
                  <button key={d.username} type="button" className={`demo-chip role-${d.username}`} onClick={() => fillDemo(d)} title={`Fill in the ${d.role.toLowerCase()} demo sign-in`}>
                    {d.role}
                  </button>
                ))}
              </div>
            </div>
            <p className="muted small login-foot"><span className="lock" aria-hidden="true">🔒</span> Only admins see names and account numbers in full. Every sign-in is recorded.</p>
          </form>
        </div>
      </section>

      <section id="how" className="landing-section">
        <h2 className="section-title reveal">How it works</h2>
        <p className="section-sub reveal">From raw statements to a case file in four steps.</p>
        <ol className="how-steps">
          {STEPS.map((st, i) => (
            <li key={st.n} className="how-step reveal" style={{ transitionDelay: `${i * 120}ms` }}>
              <span className="step-n">{st.n}</span>
              <h3>{st.title}</h3>
              <p>{st.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section id="features" className="landing-section">
        <h2 className="section-title reveal">Built for investigators</h2>
        <p className="section-sub reveal">Everything needed to go from a suspicion to evidence, in one place.</p>
        <div className="feature-grid">
          {FEATURES.map((f, i) => (
            <div key={f.title} className="feature reveal" style={{ transitionDelay: `${(i % 3) * 100}ms` }}>
              <span className="feature-icon">{f.icon}</span>
              <h3>{f.title}</h3>
              <p>{f.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="landing-cta reveal">
        <h2>Ready to follow the money?</h2>
        <button type="button" className="cta" onClick={goToSignIn}>Sign in to Trace360 <span aria-hidden="true">→</span></button>
      </section>

      <footer className="landing-foot">Trace360 · mule account detection with explainable AI and graph analytics</footer>
    </div>
  );
}
