import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { Account, Complaints, Data, Leads, Models, MoneyTrail, Network, NotFound, Overview } from "./pages";

/** 20px line icons (stroke = currentColor) so the sidebar needs no icon library. */
const icon = (d: ReactNode) => (
  <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>
);
const ICONS = {
  overview: icon(<><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></>),
  leads: icon(<><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="4" /><circle cx="12" cy="12" r="0.8" fill="currentColor" /></>),
  trail: icon(<><circle cx="5" cy="6" r="2" /><circle cx="19" cy="18" r="2" /><path d="M7 6h7a3 3 0 0 1 0 6h-4a3 3 0 0 0 0 6h7" /></>),
  network: icon(<><circle cx="12" cy="5" r="2" /><circle cx="5" cy="18" r="2" /><circle cx="19" cy="18" r="2" /><path d="M11 7 6 16M13 7l5 9M7 18h10" /></>),
  complaints: icon(<><path d="M12 3 2.5 20h19L12 3Z" /><path d="M12 10v4M12 17.5v.01" /></>),
  models: icon(<><rect x="5" y="5" width="14" height="14" rx="2" /><rect x="9" y="9" width="6" height="6" rx="1" /><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3" /></>),
  data: icon(<><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5" /><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" /></>),
};

const NAV = [
  { to: "/", label: "Overview", hint: "What the investigation found", icon: ICONS.overview },
  { to: "/leads", label: "Leads", hint: "Accounts ranked by risk", icon: ICONS.leads },
  { to: "/trail", label: "Money Trail", hint: "Follow money between accounts", icon: ICONS.trail },
  { to: "/network", label: "Network", hint: "Rings and shared counterparties", icon: ICONS.network },
  { to: "/complaints", label: "Complaints", hint: "Victim reports matched to accounts", icon: ICONS.complaints },
  { to: "/models", label: "Models", hint: "How the scores are made", icon: ICONS.models },
  { to: "/data", label: "Data", hint: "Upload statements, re-run", icon: ICONS.data },
];

export default function App() {
  const [open, setOpen] = useState(false); // sidebar drawer on narrow screens
  const { pathname } = useLocation();
  useEffect(() => setOpen(false), [pathname]);

  return (
    <div className={`app${open ? " nav-open" : ""}`}>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">T</span>
          <span>
            <span className="brand-name">Trace360</span>
            <span className="brand-sub">Mule account detection</span>
          </span>
        </div>
        <nav>
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"} className={({ isActive }) =>
              `nav-item${isActive || (n.to === "/leads" && pathname.startsWith("/accounts")) ? " active" : ""}`}>
              {n.icon}
              <span><span className="nav-label">{n.label}</span><span className="nav-hint">{n.hint}</span></span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span className="lock" aria-hidden="true">🔒</span> Names, account numbers and UPI ids are masked on every screen.
        </div>
      </aside>
      <div className="scrim" onClick={() => setOpen(false)} />
      <div className="content">
        <div className="topbar">
          <button className="menu-btn" onClick={() => setOpen(true)} aria-label="Open menu">☰</button>
          <span className="brand-name">Trace360</span>
        </div>
        <main>
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/leads" element={<Leads />} />
            <Route path="/accounts/:id" element={<Account />} />
            <Route path="/trail" element={<MoneyTrail />} />
            <Route path="/trail/:id" element={<MoneyTrail />} />
            <Route path="/network" element={<Network />} />
            <Route path="/network/:ringId" element={<Network />} />
            <Route path="/complaints" element={<Complaints />} />
            <Route path="/models" element={<Models />} />
            <Route path="/data" element={<Data />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
