import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { Tier } from "../api/types";
import { Async, RoleBadge, TierBadge, num, score } from "../components";
import { useLeads } from "../hooks";

export function Leads() {
  const [tier, setTier] = useState<Tier | "">("");
  const [role, setRole] = useState("");
  const [ringOnly, setRingOnly] = useState(false);
  const leads = useLeads(tier || undefined);
  const roles = useMemo(() => Array.from(new Set((leads.data ?? []).map((l) => l.role).filter(Boolean))) as string[], [leads.data]);

  return (
    <div>
      <h1>Leads</h1>
      <p className="muted">Every account ranked by risk. Phase 2 = rules + network + anomaly uplift; Phase 1 = rules + network only.</p>
      <div className="controls">
        <label>Level <select value={tier} onChange={(e) => setTier(e.target.value as Tier | "")}>
          <option value="">all</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option>
        </select></label>
        <label>Role <select value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="">all</option>{roles.map((r) => <option key={r}>{r}</option>)}
        </select></label>
        <label><input type="checkbox" checked={ringOnly} onChange={(e) => setRingOnly(e.target.checked)} /> in a ring only</label>
      </div>
      <Async state={leads} what="leads">
        {(all) => {
          const rows = all.filter((l) => (!role || l.role === role) && (!ringOnly || l.ring_id));
          return rows.length === 0 ? <p className="muted">No accounts match these filters.</p> : (
            <table>
              <thead><tr>
                <th>#</th><th>Account</th><th className="num">Risk</th><th className="num">Phase 1</th><th className="num">Anomaly uplift</th>
                <th>Level</th><th>Role</th><th>Ring</th><th className="num">Flagged weeks</th><th className="num">Txns</th><th>Top reason</th>
              </tr></thead>
              <tbody>
                {rows.map((l) => (
                  <tr key={l.account_id}>
                    <td>{l.rank}</td>
                    <td><Link to={`/accounts/${l.account_id}`}>{l.account_id}</Link></td>
                    <td className="num"><b>{score(l.risk_score)}</b></td>
                    <td className="num">{score(l.risk_score_phase1)}</td>
                    <td className="num">{l.anomaly_score == null ? <span className="muted" title="no reliable timestamps">n/a</span> : `+${score(l.anomaly_uplift)}`}</td>
                    <td><TierBadge tier={l.tier} /></td>
                    <td><RoleBadge role={l.role} /></td>
                    <td>{l.ring_id ? <Link to={`/network/${l.ring_id}`}>{l.ring_id}</Link> : "—"}</td>
                    <td className="num">{l.flagged_weeks ?? "n/a"}</td>
                    <td className="num">{num(l.n_rows)}</td>
                    <td className="small">{l.top_reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          );
        }}
      </Async>
    </div>
  );
}
