import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Account, Complaints, Data, Leads, Login, Models, MoneyTrail, Network, NotFound, Overview, Users } from "./pages";
import { ErrorBox, ICONS, Loading } from "./components";
import { useAuth } from "./hooks";
import type { UserRole as Role } from "./api";

const NAV: { to: string; label: string; hint: string; icon: JSX.Element; role?: Role }[] = [
  { to: "/ingestion", label: "Ingestion", hint: "Upload statements, re-run", icon: ICONS.data, role: "admin" },
  { to: "/", label: "Dashboard", hint: "What the investigation found", icon: ICONS.overview },
  { to: "/trail", label: "Money Trail", hint: "Follow money between accounts", icon: ICONS.trail },
  { to: "/leads", label: "Leads", hint: "Accounts ranked by risk", icon: ICONS.leads },
  { to: "/network", label: "Network", hint: "Rings and shared counterparties", icon: ICONS.network },
  { to: "/complaints", label: "Complaints", hint: "Victim reports matched to accounts", icon: ICONS.complaints },
  { to: "/models", label: "Models", hint: "How the scores are made", icon: ICONS.models },
  { to: "/users", label: "Users", hint: "Who can sign in, audit log", icon: ICONS.users, role: "admin" },
];

const ROLE_LABEL: Record<Role, string> = { viewer: "Viewer", investigator: "Investigator", admin: "Admin" };

/** Shown instead of a screen the signed-in role may not use (the API refuses it too). */
const NeedsRole = ({ role }: { role: Role }) => (
  <div><h1>Not available</h1><p className="muted role-note">This screen needs the {ROLE_LABEL[role].toLowerCase()} role. Ask an admin if you need it.</p></div>
);

export default function App() {
  const { me, error, retry } = useAuth();
  if (error) return <div className="login-page"><ErrorBox error={error} onRetry={retry} /></div>;
  if (me === undefined) return <div className="login-page"><Loading what="Trace360" /></div>;
  if (me === null) return <Login />;
  return <Shell />;
}

function Shell() {
  const { me, can, signOut } = useAuth();
  const [open, setOpen] = useState(false); // sidebar drawer on narrow screens
  const { pathname } = useLocation();
  useEffect(() => setOpen(false), [pathname]);
  const user = me!.user;

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
          {NAV.filter((n) => !n.role || can(n.role)).map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"} className={({ isActive }) =>
              `nav-item${isActive || (n.to === "/leads" && pathname.startsWith("/accounts")) ? " active" : ""}`}>
              {n.icon}
              <span><span className="nav-label">{n.label}</span><span className="nav-hint">{n.hint}</span></span>
            </NavLink>
          ))}
        </nav>
        <div className="user-box">
          <span className="user-avatar" aria-hidden="true">{(user.display_name || user.username).charAt(0).toUpperCase()}</span>
          <span className="user-text">
            <span className="user-name">{user.display_name || user.username}</span>
            <span className={`user-role role-${user.role}`}>{ROLE_LABEL[user.role]}{me!.unmasked ? " · unmasked" : " · masked"}</span>
          </span>
          {me!.auth_enabled && <button type="button" className="signout" onClick={signOut} title="Sign out">Sign out</button>}
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
            <Route path="/ingestion" element={can("admin") ? <Data /> : <NeedsRole role="admin" />} />
            <Route path="/users" element={can("admin") ? <Users /> : <NeedsRole role="admin" />} />
            <Route path="/data" element={<Navigate to="/ingestion" replace />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
