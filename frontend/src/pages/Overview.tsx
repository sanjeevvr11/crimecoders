import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Async, RoleBadge, StatTile, TierBadge, num, score } from "../components";
import { useAlerts, useStats } from "../hooks";

const STAGES = [
  ["1. Ingest", "25 bank statements in 5 different layouts are read and mapped to one common transaction table (494k rows). Only ICORE statements have usable timestamps; balances are randomised and ignored."],
  ["2. Parse narrations", "UPI / IMPS / NEFT text is parsed for the channel and the counterparty (UPI id, account, IFSC). Identifiers are masked everywhere in the UI."],
  ["3. Rule indicators", "Explainable mule traits per account: pass-through, many payers (fan-in), many payees (fan-out), money leaving within 2 hours, night activity, bursts, round amounts."],
  ["4. Money-flow graph", "Accounts and counterparties form a network. Louvain finds rings of accounts sharing counterparties; PageRank and betweenness find hubs and bridges."],
  ["5. Unsupervised models", "Isolation Forest flags unusual weeks (vs all weeks and vs the account's own history), SHAP explains each flag, HDBSCAN names behaviour roles (collector / distributor / layering)."],
  ["6. Risk score & leads", "Rules + network form the base score (0-100); unusual weeks add an uplift. Accounts above the threshold become alerts with their top reasons and a PDF evidence report."],
];

export function Overview() {
  const stats = useStats();
  const alerts = useAlerts();
  const [running, setRunning] = useState(false);
  const [runMsg, setRunMsg] = useState<string>();

  const rerun = async () => {
    setRunning(true);
    setRunMsg(undefined);
    try {
      const r = await api.runPipeline();
      setRunMsg(`Pipeline finished: ${num(r.stats.n_transactions)} transactions, ${r.stats.n_alerts} alerts.`);
      stats.reload();
      alerts.reload();
    } catch (e) {
      setRunMsg(`Pipeline failed: ${(e as Error).message}`);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div>
      <h1>Overview</h1>
      <Async state={stats} what="statistics">
        {(s) => (
          <>
            <div className="tiles">
              <StatTile label="Transactions" value={num(s.n_transactions)} hint={`${s.n_accounts} accounts`} />
              <StatTile label="Alerts" value={s.n_alerts} hint={`risk ≥ ${s.alert_threshold}`} />
              <StatTile label="Rings" value={s.n_rings} hint={`${num(s.n_shared_counterparties)} shared counterparties`} />
              <StatTile label="Narrations parsed" value={`${s.pct_text_narrations_parsed}%`} hint={`of ${num(s.narrations_with_text)} with real text`} />
              <StatTile label="Flagged weeks" value={String(s.models?.flagged_windows ?? "—")} hint={`of ${s.models?.windows ?? "—"} account-weeks`} />
              <StatTile label="Complaints matched" value={`${s.complaints.matched}/${s.complaints.complaints}`} hint="synthetic complaints" />
            </div>
            <p className="muted">Data generated {s.generated_at}.{" "}
              <button onClick={rerun} disabled={running}>{running ? "Running pipeline (~1 min)…" : "Re-run pipeline"}</button>{" "}
              {runMsg}
            </p>
          </>
        )}
      </Async>

      <h2>Alerts</h2>
      <Async state={alerts} what="alerts" isEmpty={(a) => a.length === 0} empty="No account is above the alert threshold.">
        {(list) => (
          <table>
            <thead><tr><th>#</th><th>Account</th><th className="num">Risk</th><th>Level</th><th>Role</th><th>Ring</th><th>Top reason</th></tr></thead>
            <tbody>
              {list.map((a) => (
                <tr key={a.alert_id}>
                  <td>{a.rank}</td>
                  <td><Link to={`/accounts/${a.account_id}`}>{a.account_id}</Link></td>
                  <td className="num"><b>{score(a.risk_score)}</b></td>
                  <td><TierBadge tier={a.tier} /></td>
                  <td><RoleBadge role={a.role} /></td>
                  <td>{a.ring_id ? <Link to={`/network/${a.ring_id}`}>{a.ring_id}</Link> : "—"}</td>
                  <td className="small">{a.top_reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Async>

      <h2>How Trace360 works</h2>
      <div className="stages">
        {STAGES.map(([t, d]) => (
          <div className="stage" key={t}><b>{t}</b><p>{d}</p></div>
        ))}
      </div>
      <p className="muted">Leads are prompts for investigation, not findings. There are no fraud labels in the data, so model quality is measured with a synthetic test. See <Link to="/models">Models</Link>.</p>
    </div>
  );
}
