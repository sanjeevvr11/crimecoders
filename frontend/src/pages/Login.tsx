import { useEffect, useRef, useState, type FormEvent, type MouseEvent } from "react";
import { ApiError } from "../api";
import { useAuth } from "../hooks";
import "./landing.css";

/**
 * Landing page cum sign-in, built from Dhanya's "Trace360 Landing v3" design:
 * a scroll-driven radar hero (the ring traces 360° as you scroll, then the
 * title shrinks and the pitch fades in), the sign-in card, How it works,
 * Features and a call to action with a live risk-score gauge. Motion is off
 * for people who ask for reduced motion.
 */

const ROLES: { name: string; username: string; password: string; c: string }[] = [
  { name: "Admin", username: "admin", password: "Trace360-Admin", c: "#F0344F" },
  { name: "Investigator", username: "investigator", password: "Trace360-Investigator", c: "#F59E2B" },
  { name: "Viewer", username: "viewer", password: "Trace360-Viewer", c: "#4C7BF0" },
];

const STEPS = [
  { n: "01", c: "#F0344F", title: "Ingest", body: "Upload statements in any of six bank layouts. Each one is read into a single, clean format automatically." },
  { n: "02", c: "#F59E2B", title: "Score", body: "Eleven mule traits, such as money leaving within hours or bursts at night, build a risk score from 0 to 100." },
  { n: "03", c: "#F7C948", title: "Map", body: "A money-flow network reveals rings of linked accounts and follows funds from one account to the next." },
  { n: "04", c: "#4C7BF0", title: "Explain", body: "Machine learning flags unusual weeks and says why. Every account gets a downloadable evidence report." },
];

const SCREENS = [
  { tag: "Dashboard", c: "#F0344F", name: "Investigation summary", body: "One conclusion up front: how many accounts need attention and which tier each one sits in." },
  { tag: "Leads", c: "#F59E2B", name: "Accounts ranked by risk", body: "Filter by tier, behaviour role or ring and open any account to see why it scored the way it did." },
  { tag: "Money Trail", c: "#F7C948", name: "Follow the money", body: "Trace funds forward or backward across accounts to see where money came from and where it went." },
  { tag: "Network", c: "#8B6CF0", name: "Rings and shared contacts", body: "Explore an interactive graph of linked accounts and the counterparties they share." },
  { tag: "Complaints", c: "#4C7BF0", name: "Victim reports matched", body: "Connect victim complaints to the accounts that received the money, with a match confidence." },
  { tag: "Users", c: "#AEB6C7", name: "Roles and audit log", body: "Admin, Investigator and Viewer roles control who sees what. Every sign-in is recorded." },
];

const TIERS = [
  { label: "Priority investigation", c: "#F0344F" },
  { label: "Investigate", c: "#F59E2B" },
  { label: "Watchlist", c: "#F7C948" },
  { label: "No action now", c: "#4C7BF0" },
];

const LAST_USER = "trace360:last-user";

export function Login() {
  const { signIn } = useAuth();
  const root = useRef<HTMLDivElement>(null);
  const userInput = useRef<HTMLInputElement>(null);
  const [user, setUser] = useState(() => { try { return localStorage.getItem(LAST_USER) ?? ""; } catch { return ""; } });
  const [pass, setPass] = useState("");
  const [show, setShow] = useState(false);
  const [signing, setSigning] = useState(false);
  const [error, setError] = useState<string>();
  const can = !!(user.trim() && pass);
  // the opening sequence starts once the font is in, so the title doesn't jump mid-animation
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let on = true;
    const go = () => on && setReady(true);
    Promise.race([document.fonts?.ready ?? Promise.resolve(), new Promise((r) => setTimeout(r, 900))]).then(go, go);
    return () => { on = false; };
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!can || signing) return;
    setSigning(true);
    setError(undefined);
    try {
      await signIn(user.trim(), pass);
      try { localStorage.setItem(LAST_USER, user.trim()); } catch { /* storage blocked */ }
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 500 ? err.message.charAt(0).toUpperCase() + err.message.slice(1) + "." : "Could not reach the server. Is the API running (make dev)?");
      setPass("");
      setSigning(false);
    }
  };

  /** in-page links scroll smoothly (instantly with reduced motion); sign-in links also focus the form */
  const jump = (id: string) => (e: MouseEvent) => {
    e.preventDefault();
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    document.getElementById(id)?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: id === "signin" ? "center" : "start" });
    if (id === "signin") setTimeout(() => userInput.current?.focus({ preventScroll: true }), reduce ? 0 : 600);
  };

  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const stops = [startRadar(el, reduce), startHeroScroll(el), startGauge(el, reduce)];
    if (!reduce) stops.push(startReveal(el));
    return () => stops.forEach((stop) => stop());
  }, []);

  return (
    <div className={`lp${ready ? " lp-ready" : ""}`} ref={root}>
      <header className="lp-header lp-intro-down">
        <div className="lp-header-in">
          <a href="#top" data-h="hdrlogo" className="lp-logo" onClick={jump("top")}>
            <img src="/trace360-icon.png" alt="" aria-hidden="true" />
            <span className="lp-logo-text">
              <span className="lp-logo-name">Trace<span className="red">360</span></span>
              <span className="lp-logo-sub">Mule account detection</span>
            </span>
          </a>
          <nav className="lp-nav">
            <a href="#how" onClick={jump("how")}>How it works</a>
            <a href="#features" onClick={jump("features")}>Features</a>
            <a href="#signin" className="lp-btn-red lp-nav-signin" onClick={jump("signin")}>Sign in</a>
          </nav>
        </div>
      </header>

      <div data-h="net" className="lp-net" aria-hidden="true" />
      <section id="top" className="lp-hero">
        <div className="lp-hero-stage">
          <div data-h="block" className="lp-hero-block">
            <div className="lp-hero-title">
              <svg data-h="ringsvg" viewBox="0 0 100 100" className="lp-ring" aria-hidden="true">
                <circle className="lp-ring-track" cx="50" cy="50" r="49" fill="none" stroke="#1E2A40" strokeWidth="0.2" pathLength={360} strokeDasharray="360" />
                <circle className="lp-ring-ping" cx="50" cy="50" r="49" fill="none" stroke="#F0344F" strokeWidth="0.3" />
                <circle data-h="ring" cx="50" cy="50" r="49" fill="none" stroke="#F0344F" strokeWidth="0.45" strokeLinecap="round" pathLength={360}
                  strokeDasharray="360" strokeDashoffset="360" style={{ filter: "drop-shadow(0 0 1.2px #F0344F)" }} />
                <circle data-h="dot" cx="99" cy="50" r="1.1" fill="#FFD2D8" style={{ transformOrigin: "50px 50px", filter: "drop-shadow(0 0 1.5px #F0344F)" }} />
              </svg>
              <h1 aria-label="Trace360">
                {[..."Trace"].map((ch, i) => <span key={i} className="lp-l" style={{ animationDelay: `${450 + i * 70}ms` }} aria-hidden="true">{ch}</span>)}
                <span className="lp-360" aria-hidden="true">360</span>
              </h1>
            </div>
            <div className="lp-hero-sub lp-intro" style={{ animationDelay: "1250ms" }}>
              <span>Mule account detection</span><span className="lp-dot" /><span data-h="deg" className="lp-deg">000°</span>
            </div>
          </div>
          <div data-h="copy" className="lp-hero-copy">
            <h2>Trace the money. <span className="red">Find the mules.</span></h2>
            <p>Trace360 reads bank statements, scores every account with reasons you can explain, maps who moves money to whom, and turns it into evidence an investigator can act on.</p>
            <div className="lp-ctas">
              <a href="#signin" className="lp-btn-red lp-btn-lg" onClick={jump("signin")}>Start investigating <span>→</span></a>
              <a href="#how" className="lp-btn-ghost lp-btn-lg" onClick={jump("how")}>See how it works</a>
            </div>
          </div>
          <div data-h="hint" className="lp-hint" aria-hidden="true">
            <span className="lp-intro" style={{ animationDelay: "1700ms" }}>Scroll to trace</span><span className="lp-hint-line lp-intro" style={{ animationDelay: "1800ms" }} />
          </div>
        </div>
      </section>

      <section data-screen="signin" className="lp-signin-sec">
        <div className="lp-pitch">
          <div className="lp-col12">
            <span className="lp-eyebrow">Built for investigators</span>
            <h2 className="lp-h2-md">Every account sorted into what to do next.</h2>
            <p className="lp-lead">Scores from 0 to 100 place each account into an action tier, and every score comes with the reasons behind it.</p>
          </div>
          <div className="lp-col14">
            <div data-tierbar="1" className="lp-tierbar">
              {TIERS.map((t, i) => <span key={t.label} data-seg={i} style={{ background: t.c }} />)}
            </div>
            <div className="lp-tier-legend">
              {TIERS.map((t) => <span key={t.label}><span className="lp-swatch" style={{ background: t.c }} />{t.label}</span>)}
            </div>
          </div>
          <div className="lp-points">
            <div><b>Explainable</b><span>Top five reasons in plain English for every score.</span></div>
            <div><b>Private by default</b><span>Identifiers are masked; only admins see them in full.</span></div>
            <div><b>Leads, not verdicts</b><span>Scores point an investigator where to look first.</span></div>
          </div>
        </div>

        <div id="signin" className="lp-card">
          <form onSubmit={submit} className="lp-form">
            <div className="lp-col8">
              <h2 className="lp-card-title">Sign in</h2>
              <p className="lp-card-sub">Welcome back. Use the account your administrator gave you.</p>
            </div>
            <label className="lp-label">User name
              <input ref={userInput} className="lp-input" type="text" value={user} onChange={(e) => { setUser(e.target.value); setError(undefined); }}
                placeholder="Enter your user name" autoComplete="username" />
            </label>
            <label className="lp-label">Password
              <span className="lp-pw">
                <input className="lp-input lp-input-pw" type={show ? "text" : "password"} value={pass} onChange={(e) => { setPass(e.target.value); setError(undefined); }}
                  placeholder="Enter your password" autoComplete="current-password" />
                <button type="button" className="lp-show" onClick={() => setShow(!show)} aria-pressed={show}>{show ? "Hide" : "Show"}</button>
              </span>
            </label>
            {error && <div className="lp-error" role="alert">{error}</div>}
            <button type="submit" className={`lp-submit${can ? " on" : ""}`} disabled={!can || signing}>
              {signing ? `Signing in as ${user.trim()}…` : "Sign in"}
            </button>
            <div className="lp-demo">
              <span>Demo access</span>
              <div className="lp-demo-grid">
                {ROLES.map((r) => {
                  const on = user === r.username;
                  return (
                    <button key={r.name} type="button" className="lp-role" onClick={() => { setUser(r.username); setPass(r.password); setError(undefined); }}
                      style={{ borderColor: r.c, background: on ? r.c : "transparent", color: on ? "#FFFFFF" : r.c }}>{r.name}</button>
                  );
                })}
              </div>
            </div>
            <p className="lp-recorded">Every sign-in is recorded.</p>
          </form>
        </div>
      </section>

      <section id="how" className="lp-sec">
        <div className="lp-sec-in">
          <div className="lp-sec-head">
            <span className="lp-eyebrow">How it works</span>
            <h2 className="lp-h2-lg">From raw statements to evidence, in one run.</h2>
          </div>
          <div className="lp-pairs">
            {[STEPS.slice(0, 2), STEPS.slice(2)].map((pair, i) => (
              <div key={i} className="lp-pair">
                {pair.map((s) => (
                  <div key={s.n} className="lp-step" style={{ borderTopColor: s.c }}>
                    <span className="lp-step-n" style={{ color: s.c }}>STEP {s.n}</span>
                    <span className="lp-step-title">{s.title}</span>
                    <span className="lp-body">{s.body}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="features" className="lp-sec">
        <div className="lp-sec-in">
          <div className="lp-sec-head">
            <span className="lp-eyebrow">Features</span>
            <h2 className="lp-h2-lg">Everything an investigation needs, in one place.</h2>
          </div>
          <div className="lp-features">
            {SCREENS.map((f) => (
              <div key={f.tag} className="lp-feature">
                <span className="lp-tag" style={{ borderColor: f.c, color: f.c }}>{f.tag}</span>
                <span className="lp-feature-name">{f.name}</span>
                <span className="lp-body">{f.body}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section data-screen="cta" className="lp-cta-sec">
        <div className="lp-cta">
          <div className="lp-cta-copy">
            <span className="lp-eyebrow">Get started</span>
            <h2 className="lp-h2-cta">Ready to follow<br />the money?</h2>
            <p>Sign in with the account your administrator gave you and pick up where the last run left off.</p>
            <div className="lp-ctas lp-ctas-left">
              <a href="#signin" className="lp-btn-red lp-btn-lg" onClick={jump("signin")}>Sign in <span>→</span></a>
              <a href="#how" className="lp-btn-ghost lp-btn-lg" onClick={jump("how")}>How it works</a>
            </div>
          </div>
          <div aria-hidden="true" className="lp-cta-gauge"><div data-cta-flow="1" /></div>
        </div>
      </section>

      <footer className="lp-footer">
        <div className="lp-footer-in">
          <span><span className="lp-footer-name">Trace<span className="red">360</span></span> · Mule account detection</span>
          <span>Scores are leads for an investigator to confirm, not proof of fraud.</span>
        </div>
      </footer>
    </div>
  );
}

/* ---------------------------------------------------------------- animations */

type Stop = () => void;

/** canvas inside `host` that follows its size; returns the context and a size getter */
function hostCanvas(host: HTMLElement) {
  const cv = document.createElement("canvas");
  cv.style.cssText = "width:100%;height:100%;display:block;";
  host.innerHTML = "";
  host.appendChild(cv);
  const ctx = cv.getContext("2d")!;
  const box = { W: 0, H: 0 };
  const size = () => {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    box.W = host.clientWidth; box.H = host.clientHeight;
    cv.width = box.W * dpr; cv.height = box.H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  };
  size();
  return { ctx, box, size };
}

/** shared between the hero scroll and the radar: how far past the hero the page is (0..1) */
const scrollState = { after: 0 };

/** full-page radar: a sweep turns every 9 s and lights up blips; red blips pulse. Calms down below the hero. */
function startRadar(root: HTMLElement, reduce: boolean): Stop {
  const host = root.querySelector<HTMLElement>('[data-h="net"]');
  if (!host) return () => {};
  const { ctx, box, size } = hostCanvas(host);
  let cx = 0, cy = 0, R = 0, raf = 0;
  let blips: { ang: number; rad: number; hot: boolean }[] = [];
  const build = () => {
    size();
    cx = box.W / 2; cy = box.H / 2; R = Math.hypot(box.W, box.H) / 2;
    blips = Array.from({ length: 34 }, () => ({ ang: Math.random() * Math.PI * 2, rad: 120 + Math.random() * (R - 140), hot: Math.random() < 0.2 }));
  };
  build();
  addEventListener("resize", build);
  const period = 9000;
  const draw = (t: number) => {
    const { W, H } = box;
    const sweep = reduce ? Math.PI * 1.3 : ((t % period) / period) * Math.PI * 2;
    const af = scrollState.after, sk = 1 - 0.8 * af;
    ctx.clearRect(0, 0, W, H);
    ctx.lineWidth = 1;
    for (let r = 140; r < R; r += 140) { ctx.strokeStyle = "rgba(120,136,175,0.09)"; ctx.beginPath(); ctx.arc(cx, cy, r, 0, 6.283); ctx.stroke(); }
    ctx.strokeStyle = "rgba(120,136,175,0.06)"; ctx.beginPath(); ctx.moveTo(cx - R, cy); ctx.lineTo(cx + R, cy); ctx.moveTo(cx, cy - R); ctx.lineTo(cx, cy + R); ctx.stroke();
    if (ctx.createConicGradient) {
      const g = ctx.createConicGradient(sweep - 0.9, cx, cy);
      g.addColorStop(0, "rgba(240,52,79,0)"); g.addColorStop(0.143, `rgba(240,52,79,${0.13 * sk})`); g.addColorStop(0.1432, "rgba(240,52,79,0)"); g.addColorStop(1, "rgba(240,52,79,0)");
      ctx.fillStyle = g; ctx.beginPath(); ctx.moveTo(cx, cy); ctx.arc(cx, cy, R, 0, 6.283); ctx.fill();
    }
    ctx.strokeStyle = `rgba(240,52,79,${0.35 * sk})`; ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + Math.cos(sweep) * R, cy + Math.sin(sweep) * R); ctx.stroke();
    for (const b of blips) {
      let diff = (sweep - b.ang) % (Math.PI * 2); if (diff < 0) diff += Math.PI * 2;
      const swept = reduce ? (b.hot ? 0.6 : 0.3) : Math.max(0, 1 - diff / (Math.PI * 1.4));
      const tw = 0.25 + 0.25 * Math.sin(t / 1400 + b.ang * 7);
      const k = swept * sk + tw * af;
      if (k <= 0.01) continue;
      const x = cx + Math.cos(b.ang) * b.rad, y = cy + Math.sin(b.ang) * b.rad;
      if (b.hot) {
        ctx.fillStyle = `rgba(240,52,79,${0.9 * k})`; ctx.beginPath(); ctx.arc(x, y, 3, 0, 6.283); ctx.fill();
        ctx.strokeStyle = `rgba(240,52,79,${0.5 * k})`; ctx.beginPath(); ctx.arc(x, y, 4 + (1 - k) * 16, 0, 6.283); ctx.stroke();
      } else { ctx.fillStyle = `rgba(170,182,210,${0.55 * k})`; ctx.beginPath(); ctx.arc(x, y, 1.8, 0, 6.283); ctx.fill(); }
    }
    if (af > 0.01 && !reduce) {
      const rp = 6000;
      for (let i = 0; i < 3; i++) {
        const ph = ((t + (i * rp) / 3) % rp) / rp, rr = ph * R;
        ctx.strokeStyle = `rgba(240,52,79,${0.16 * af * (1 - ph)})`; ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.arc(cx, cy, rr, 0, 6.283); ctx.stroke();
      }
      ctx.lineWidth = 1;
      blips.forEach((b) => { b.ang += 0.00012; });
    }
    const vg = ctx.createRadialGradient(cx, cy, R * 0.35, cx, cy, R); vg.addColorStop(0, "rgba(7,11,22,0)"); vg.addColorStop(1, "rgba(7,11,22,0.9)");
    ctx.fillStyle = vg; ctx.fillRect(0, 0, W, H);
    if (!reduce) raf = requestAnimationFrame(draw);
  };
  raf = requestAnimationFrame(draw);
  return () => { cancelAnimationFrame(raf); removeEventListener("resize", build); };
}

/**
 * The hero is 260vh tall with a sticky stage: scrolling traces the ring round
 * 360°, then shrinks the title and fades the pitch in. Once finished, the hero
 * collapses to one screen so scrolling back up doesn't replay it.
 */
function startHeroScroll(root: HTMLElement): Stop {
  const q = (k: string) => root.querySelector<HTMLElement>(`[data-h="${k}"]`)!;
  const hero = root.querySelector<HTMLElement>("#top");
  if (!hero) return () => {};
  const block = q("block"), copy = q("copy"), ring = q("ring"), dot = q("dot"), deg = q("deg"), hint = q("hint"), ringsvg = q("ringsvg"), logo = q("hdrlogo");
  const cl = (x: number, a: number, b: number) => Math.min(1, Math.max(0, (x - a) / (b - a)));
  const ease = (t: number) => 1 - Math.pow(1 - t, 3);
  let done = false;
  const onScroll = () => {
    const r = hero.getBoundingClientRect(), H = innerHeight;
    const raw = cl(-r.top, 0, r.height - H);
    if (raw >= 0.995 && !done) {
      done = true;
      const removed = hero.offsetHeight - H;
      hero.style.height = "100vh";
      window.scrollTo({ top: Math.max(0, scrollY - removed), behavior: "instant" as ScrollBehavior });
    }
    const p = done ? 1 : raw;
    scrollState.after = cl(-r.top - (r.height - H), 0, H * 0.8);
    const d = ease(cl(p, 0, 0.55)), m = ease(cl(p, 0.5, 0.85)), c = ease(cl(p, 0.62, 1));
    ring.setAttribute("stroke-dashoffset", String(360 - 360 * d));
    dot.style.transform = `rotate(${360 * d}deg)`; dot.style.opacity = d > 0.01 && d < 0.999 ? "1" : "0";
    deg.textContent = String(Math.round(360 * d)).padStart(3, "0") + "°";
    const S = 0.52, sc = 1 - (1 - S) * m, bh = block.offsetHeight, ch = copy.offsetHeight, gap = 48, hdr = 71;
    const top0 = hdr + Math.max(16, (H - hdr - (bh * S + gap + ch)) / 2);
    const cyB = H / 2 + (top0 + (bh * S) / 2 - H / 2) * m;
    block.style.top = cyB + "px";
    block.style.transform = `translate(-50%,-50%) scale(${sc})`;
    copy.style.top = top0 + bh * S + gap + "px";
    ringsvg.style.opacity = String(1 - m);
    copy.style.opacity = String(c); copy.style.transform = `translate(-50%,${40 - 40 * c}px)`;
    copy.style.pointerEvents = c > 0.5 ? "auto" : "none";
    hint.style.opacity = String(1 - cl(p, 0, 0.12));
    logo.style.opacity = p > 0.97 || r.bottom < H ? "1" : "0";
  };
  addEventListener("scroll", onScroll, { passive: true });
  addEventListener("resize", onScroll);
  onScroll();
  return () => { removeEventListener("scroll", onScroll); removeEventListener("resize", onScroll); scrollState.after = 0; };
}

/** risk-score gauge in the call to action: sweeps up to a score, holds, drops, next score */
function startGauge(root: HTMLElement, reduce: boolean): Stop {
  const host = root.querySelector<HTMLElement>("[data-cta-flow]");
  if (!host) return () => {};
  const { ctx, box, size } = hostCanvas(host);
  const ro = new ResizeObserver(size);
  ro.observe(host);
  const tiers: [number, string, string][] = [[70, "#F0344F", "PRIORITY INVESTIGATION"], [50, "#F59E2B", "INVESTIGATE"], [35, "#F7C948", "WATCHLIST"], [0, "#4C7BF0", "NO ACTION NOW"]];
  const tierOf = (v: number) => tiers.find((t) => v >= t[0])!;
  const targets = [28, 61, 44, 88, 73, 52];
  let ti = 0, t0: number | null = null, raf = 0;
  const A0 = Math.PI * 0.75, SPAN = Math.PI * 1.5, UP = 1600, HOLD = 1800, DOWN = 700;
  const ease = (x: number) => 1 - Math.pow(1 - x, 3);
  const font = '"Plus Jakarta Sans",sans-serif';
  const draw = (t: number) => {
    const { W, H } = box;
    if (t0 === null) t0 = t;
    let el = t - t0; const tgt = targets[ti % targets.length];
    if (el > UP + HOLD + DOWN) { ti++; t0 = t; el = 0; }
    const v = reduce ? 73 : el < UP ? tgt * ease(el / UP) : el < UP + HOLD ? tgt : tgt * (1 - ease((el - UP - HOLD) / DOWN));
    const cx = W / 2, cy = H / 2 + 12, R = Math.min(W * 0.38, H * 0.4);
    ctx.clearRect(0, 0, W, H);
    for (let i = 0; i <= 100; i += 2) {
      const ang = A0 + (SPAN * i) / 100, major = i % 10 === 0, on = i <= v;
      const r1 = R + 10, r2 = R + (major ? 22 : 16);
      ctx.strokeStyle = on ? tierOf(i)[1] : `rgba(120,136,175,${major ? 0.35 : 0.18})`; ctx.lineWidth = major ? 2 : 1.2; ctx.globalAlpha = on ? 0.9 : 1;
      ctx.beginPath(); ctx.moveTo(cx + Math.cos(ang) * r1, cy + Math.sin(ang) * r1); ctx.lineTo(cx + Math.cos(ang) * r2, cy + Math.sin(ang) * r2); ctx.stroke();
    }
    ctx.globalAlpha = 1;
    tiers.slice().reverse().forEach((tr, i, arr) => {
      const from = tr[0], to = i < arr.length - 1 ? arr[i + 1][0] : 100;
      ctx.strokeStyle = "rgba(120,136,175,0.12)"; ctx.lineWidth = 10; ctx.lineCap = "butt";
      ctx.beginPath(); ctx.arc(cx, cy, R - 8, A0 + (SPAN * from) / 100 + 0.01, A0 + (SPAN * to) / 100 - 0.01); ctx.stroke();
    });
    const T = tierOf(Math.max(0, v));
    ctx.strokeStyle = T[1]; ctx.lineWidth = 10; ctx.lineCap = "round"; ctx.shadowColor = T[1]; ctx.shadowBlur = 18;
    if (v > 0.5) { ctx.beginPath(); ctx.arc(cx, cy, R - 8, A0, A0 + (SPAN * v) / 100); ctx.stroke(); }
    ctx.shadowBlur = 0; ctx.lineCap = "butt";
    const ea = A0 + (SPAN * v) / 100; ctx.fillStyle = "#FFFFFF";
    ctx.beginPath(); ctx.arc(cx + Math.cos(ea) * (R - 8), cy + Math.sin(ea) * (R - 8), 4, 0, 6.283); ctx.fill();
    ctx.textAlign = "center"; ctx.fillStyle = "#7D879B"; ctx.font = `700 11px ${font}`;
    ctx.fillText("RISK SCORE", cx, cy - R * 0.32);
    ctx.fillStyle = "#EEF1F7"; ctx.font = `800 ${Math.round(R * 0.55)}px ${font}`;
    ctx.fillText(String(Math.round(v)), cx, cy + R * 0.16);
    ctx.fillStyle = T[1]; ctx.font = `700 12px ${font}`;
    ctx.fillText(T[2], cx, cy + R * 0.42);
    ctx.fillStyle = "#5D6880"; ctx.font = `600 11px ${font}`;
    ctx.fillText("0", cx + Math.cos(A0) * (R + 34), cy + Math.sin(A0) * (R + 34) + 4);
    ctx.fillText("100", cx + Math.cos(A0 + SPAN) * (R + 34), cy + Math.sin(A0 + SPAN) * (R + 34) + 4);
    if (!reduce) raf = requestAnimationFrame(draw);
  };
  raf = requestAnimationFrame(draw);
  return () => { cancelAnimationFrame(raf); ro.disconnect(); };
}

/** sections slide up as they scroll into view, and the tier bar grows segment by segment */
function startReveal(root: HTMLElement): Stop {
  const sel = ['[data-screen="signin"] > *', "#how .lp-sec-head", "#how .lp-step", "#features .lp-sec-head", "#features .lp-feature", '[data-screen="cta"] > div'];
  const els = [...root.querySelectorAll<HTMLElement>(sel.join(","))];
  els.forEach((el) => {
    const sib = [...el.parentElement!.children].indexOf(el);
    el.style.opacity = "0"; el.style.transform = "translateY(28px)";
    el.style.transition = `opacity .8s cubic-bezier(.2,.7,.2,1) ${sib * 90}ms, transform .8s cubic-bezier(.2,.7,.2,1) ${sib * 90}ms`;
  });
  const segs = [...root.querySelectorAll<HTMLElement>("[data-seg]")];
  segs.forEach((s, i) => { s.style.transform = "scaleX(0)"; s.style.transition = `transform .9s cubic-bezier(.2,.7,.2,1) ${400 + i * 180}ms`; });
  const io = new IntersectionObserver((es) => es.forEach((e) => {
    if (!e.isIntersecting) return;
    const t = e.target as HTMLElement;
    if (t.dataset.tierbar) segs.forEach((s) => { s.style.transform = "scaleX(1)"; });
    else {
      t.style.opacity = "1"; t.style.transform = "none";
      // hand hover lift back to CSS once the reveal has finished
      setTimeout(() => { t.style.transform = ""; t.style.transition = ""; }, 1400);
    }
    io.unobserve(t);
  }), { threshold: 0.12 });
  els.forEach((el) => io.observe(el));
  const bar = root.querySelector("[data-tierbar]");
  if (bar) io.observe(bar);
  return () => io.disconnect();
}
