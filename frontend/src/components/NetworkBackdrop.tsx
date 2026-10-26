import { useEffect, useRef } from "react";

/**
 * Animated money-network background for the landing page, drawn on a canvas
 * from made-up points (never real accounts). Dots drift, nearby dots link up,
 * pulses of "money" run along the links, and every few seconds a cluster lights
 * up crimson as if a mule ring had just been found. With reduced motion turned
 * on in the system settings it draws one still frame.
 */
export function NetworkBackdrop() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let w = 0, h = 0, raf = 0;

    type Dot = { x: number; y: number; vx: number; vy: number; r: number; hot: number };
    type Pulse = { a: number; b: number; t: number; speed: number; red: boolean };
    let dots: Dot[] = [];
    const pulses: Pulse[] = [];
    let ring: number[] = [], ringStart = -1e9;
    const LINK = 150;

    const resize = () => {
      w = canvas.clientWidth;
      h = canvas.clientHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const n = Math.round(Math.min(90, Math.max(28, (w * h) / 16000)));
      dots = Array.from({ length: n }, () => ({
        x: Math.random() * w, y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.25, vy: (Math.random() - 0.5) * 0.25,
        r: 1.2 + Math.random() * 2.2, hot: 0,
      }));
    };

    const near = (i: number) => dots.map((d, j) => ({ j, d2: (d.x - dots[i].x) ** 2 + (d.y - dots[i].y) ** 2 }))
      .filter((o) => o.j !== i && o.d2 < LINK * LINK).sort((p, q) => p.d2 - q.d2);

    const spawnPulse = (now: number) => {
      const a = Math.floor(Math.random() * dots.length);
      const n = near(a);
      if (!n.length) return;
      const red = ring.includes(a) && now - ringStart < 6000;
      pulses.push({ a, b: n[Math.floor(Math.random() * Math.min(3, n.length))].j, t: 0, speed: 0.006 + Math.random() * 0.01, red });
    };

    const findRing = (now: number) => {
      const seed = Math.floor(Math.random() * dots.length);
      ring = [seed, ...near(seed).slice(0, 4).map((o) => o.j)];
      ringStart = now;
    };

    let lastPulse = 0, lastRing = 0;
    const frame = (now: number) => {
      ctx.clearRect(0, 0, w, h);
      const ringAge = now - ringStart;
      const ringGlow = ringAge < 6000 ? Math.sin(Math.min(1, ringAge / 6000) * Math.PI) : 0;

      for (const d of dots) {
        if (!still) {
          d.x += d.vx; d.y += d.vy;
          if (d.x < -20) d.x = w + 20; if (d.x > w + 20) d.x = -20;
          if (d.y < -20) d.y = h + 20; if (d.y > h + 20) d.y = -20;
        }
      }
      // links
      for (let i = 0; i < dots.length; i++) {
        for (let j = i + 1; j < dots.length; j++) {
          const dx = dots[i].x - dots[j].x, dy = dots[i].y - dots[j].y, d2 = dx * dx + dy * dy;
          if (d2 > LINK * LINK) continue;
          const inRing = ringGlow > 0 && ring.includes(i) && ring.includes(j);
          const alpha = (1 - Math.sqrt(d2) / LINK) * (inRing ? 0.35 + 0.55 * ringGlow : 0.26);
          ctx.strokeStyle = inRing ? `rgba(255,48,79,${alpha})` : `rgba(93,125,175,${alpha})`;
          ctx.lineWidth = inRing ? 1.4 : 0.8;
          ctx.beginPath(); ctx.moveTo(dots[i].x, dots[i].y); ctx.lineTo(dots[j].x, dots[j].y); ctx.stroke();
        }
      }
      // pulses of money along links
      for (let k = pulses.length - 1; k >= 0; k--) {
        const p = pulses[k];
        p.t += p.speed;
        if (p.t >= 1) { dots[p.b].hot = 1; pulses.splice(k, 1); continue; }
        const a = dots[p.a], b = dots[p.b];
        const x = a.x + (b.x - a.x) * p.t, y = a.y + (b.y - a.y) * p.t;
        const g = ctx.createRadialGradient(x, y, 0, x, y, 7);
        g.addColorStop(0, p.red ? "rgba(255,61,129,.95)" : "rgba(120,170,255,.9)");
        g.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, 7, 0, Math.PI * 2); ctx.fill();
      }
      // dots
      dots.forEach((d, i) => {
        const inRing = ringGlow > 0 && ring.includes(i);
        d.hot = Math.max(0, d.hot - 0.02);
        const r = d.r + d.hot * 1.5 + (inRing ? 2 * ringGlow : 0);
        if (inRing || d.hot > 0) {
          ctx.fillStyle = inRing ? `rgba(255,48,79,${0.18 * ringGlow})` : `rgba(77,131,255,${0.2 * d.hot})`;
          ctx.beginPath(); ctx.arc(d.x, d.y, r * 4, 0, Math.PI * 2); ctx.fill();
        }
        ctx.fillStyle = inRing ? `rgba(255,${Math.round(80 - 40 * ringGlow)},${Math.round(110 - 30 * ringGlow)},.95)` : "rgba(160,185,225,.75)";
        ctx.beginPath(); ctx.arc(d.x, d.y, r, 0, Math.PI * 2); ctx.fill();
      });

      if (still) return;
      if (now - lastPulse > 160) { spawnPulse(now); lastPulse = now; }
      if (now - lastRing > 7500) { findRing(now); lastRing = now; }
      raf = requestAnimationFrame(frame);
    };

    resize();
    if (still) { findRing(performance.now() - 3000); frame(performance.now()); }
    else raf = requestAnimationFrame(frame);
    const ro = new ResizeObserver(() => { resize(); if (still) frame(performance.now()); });
    ro.observe(canvas);
    const onVis = () => {
      cancelAnimationFrame(raf);
      if (!document.hidden && !still) raf = requestAnimationFrame(frame);
    };
    document.addEventListener("visibilitychange", onVis);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); document.removeEventListener("visibilitychange", onVis); };
  }, []);

  return <canvas ref={ref} className="network-backdrop" aria-hidden="true" />;
}
