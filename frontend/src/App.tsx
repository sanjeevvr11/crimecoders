import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Account, Complaints, Data, Leads, Models, MoneyTrail, Network, NotFound, Overview } from "./pages";
import { ICONS } from "./components";

const NAV = [
  { to: "/ingestion", label: "Ingestion", hint: "Upload statements, re-run", icon: ICONS.data },
  { to: "/", label: "Dashboard", hint: "What the investigation found", icon: ICONS.overview },
  { to: "/trail", label: "Money Trail", hint: "Follow money between accounts", icon: ICONS.trail },
  { to: "/leads", label: "Leads", hint: "Accounts ranked by risk", icon: ICONS.leads },
  { to: "/network", label: "Network", hint: "Rings and shared counterparties", icon: ICONS.network },
  { to: "/complaints", label: "Complaints", hint: "Victim reports matched to accounts", icon: ICONS.complaints },
  { to: "/models", label: "Models", hint: "How the scores are made", icon: ICONS.models },
];

export default function App() {
  const [open, setOpen] = useState(false); // sidebar drawer on narrow screens
  const { pathname } = useLocation();
  useEffect(() => setOpen(false), [pathname]);

  return (
    <div className={`app${open ? " nav-open" : ""}`}>
      <aside className="sidebar">
        <div className="brand">
          <img className="brand-mark" src="/trace360-icon.png" alt="" aria-hidden="true" />
          <span>
            <span className="brand-name">Trace<em>360</em></span>
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
          <span className="brand-name">Trace<em>360</em></span>
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
            <Route path="/ingestion" element={<Data />} />
            <Route path="/data" element={<Navigate to="/ingestion" replace />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
