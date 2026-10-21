import { NavLink, Route, Routes } from "react-router-dom";
import { Account, Complaints, Leads, Models, Network, NotFound, Overview } from "./pages";

const NAV = [
  ["/", "Overview"], ["/leads", "Leads"], ["/network", "Network"], ["/complaints", "Complaints"], ["/models", "Models"],
] as const;

export default function App() {
  return (
    <div className="app">
      <header>
        <span className="brand">Trace360</span>
        <nav>{NAV.map(([to, label]) => <NavLink key={to} to={to} end={to === "/"}>{label}</NavLink>)}</nav>
        <span className="muted small">mule account detection · identifiers masked</span>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/leads" element={<Leads />} />
          <Route path="/accounts/:id" element={<Account />} />
          <Route path="/network" element={<Network />} />
          <Route path="/network/:ringId" element={<Network />} />
          <Route path="/complaints" element={<Complaints />} />
          <Route path="/models" element={<Models />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </div>
  );
}
