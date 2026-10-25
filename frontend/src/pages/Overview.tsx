import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { Conclusion, ConclusionAccount } from "../api/types";
import { Async, RoleBadge, StatTile, TierBadge, inr, inrShort, num, score } from "../components";
import { useConclusion, useStats } from "../hooks";

const STAGES = [
  ["1. Ingest", "25 bank statements in 5 different layouts are read and mapped to one common transaction table (494k rows). Only ICORE statements have usable timestamps; balances are randomised and ignored."],
  ["2. Parse narrations", "UPI / IMPS / NEFT text is parsed for the channel and the counterparty (UPI id, account, IFSC). Identifiers are masked everywhere in the UI."],
  ["3. Rule indicators", "Explainable mule traits per account: pass-through, many payers (fan-in), many payees (fan-out), money leaving within 2 hours, night activity, bursts, round amounts."],
  ["4. Money-flow graph", "Accounts and counterparties form a network. Louvain finds rings of accounts sharing counterparties; PageRank and betweenness find hubs and bridges."],
  ["5. Unsupervised models", "Isolation Forest flags unusual weeks (vs all weeks and vs the account's own history), SHAP explains each flag, HDBSCAN names behaviour roles (collector / distributor / layering)."],
  ["6. Risk score & leads", "Rules + network form the base score (0-100); unusual weeks add an uplift. Accounts above the threshold become alerts with their top reasons and a PDF evidence report."],
];

/** A dashboard section that shows only its heading until opened. */
function Fold({ title, open = false, children }: { title: ReactNode; open?: boolean; children: ReactNode }) {
  return (
    <details className="fold" open={open}>
      <summary><h2>{title}</h2></summary>
      <div className="fold-body">{children}</div>
    </details>
  );
}

/** Share of accounts per outcome, as one bar: high / medium / watchlist / no action. */
function OutcomeBar({ c }: { c: Conclusion["counts"] }) {
  const parts = [
    ["HIGH", c.HIGH, "Priority investigation"],
    ["MEDIUM", c.MEDIUM, "Investigate"],
    ["watch", c.watchlist, "Watchlist"],
    ["none", c.no_action, "No action now"],
  ] as const;
  return (
    <div className="outcome">
      <div className="outcome-bar">
        {parts.map(([k, n]) => n > 0 && <span key={k} className={`seg seg-${k}`} style={{ flex: n }} />)}
      </div>
      <div className="outcome-legend">
        {parts.map(([k, n, label]) => (
          <span key={k}><span className={`seg-dot seg-${k}`} /> <b>{n}</b> {label}</span>
        ))}
      </div>
    </div>
  );
}

function AccountCard({ a }: { a: ConclusionAccount }) {
  return (
    <details className={`verdict-card v-${a.tier}`}>
      <summary>
        <div className="verdict-top">
          <span className="verdict-label">{a.verdict}</span>
          <span className="verdict-score">{score(a.risk_score)}</span>
        </div>
        <div className="verdict-id">
          <Link to={`/accounts/${a.account_id}`}>{a.account_id}</Link>{" "}
          <TierBadge tier={a.tier} /> <RoleBadge role={a.role} />
          {a.ring_id && <> <Link className="badge" to={`/network/${a.ring_id}`}>ring {a.ring_id}</Link></>}
        </div>
      </summary>
      <ul className="tight small">
        {a.reasons.map((r) => <li key={r}>{r}</li>)}
      </ul>
      <div className="verdict-facts small">
        {a.trail ? (
          <span>Trail: {inrShort(a.trail.amount_in)} in · {inrShort(a.trail.amount_out)} out · {a.trail.n_cross_account_chains} cross-account chains</span>
        ) : (
          <span className="muted">No counterparties named in this statement, so no money trail.</span>
        )}
        {a.complaint_matches > 0 && <span>{a.complaint_matches} complaint{a.complaint_matches > 1 ? "s" : ""} matched</span>}
        {a.flagged_weeks ? <span>{a.flagged_weeks} unusual week{a.flagged_weeks > 1 ? "s" : ""}</span> : null}
        {a.linked_accounts.length > 0 && (
          <span>Linked to {a.linked_accounts.map((l, i) => <span key={l}>{i > 0 && ", "}<Link to={`/accounts/${l}`}>{l}</Link></span>)}</span>
        )}
      </div>
      <p className="verdict-action"><b>Next step:</b> {a.action}</p>
      <div className="verdict-links small">
        <Link to={`/accounts/${a.account_id}`}>Account details →</Link>
        {a.trail && <Link to={`/trail/${a.account_id}`}>Money trail →</Link>}
      </div>
    </details>
  );
}

function ConclusionView({ c, glance }: { c: Conclusion; glance: ReactNode }) {
  return (
    <>
      <section className="verdict-hero">
        <div className="verdict-kicker">CONCLUSION OF THE INVESTIGATION</div>
        <h2>{c.headline}</h2>
        <p>{c.summary}</p>
        <OutcomeBar c={c.counts} />
      </section>

      {glance}

      <Fold open title={<>Accounts to act on ({c.accounts.length}) <span className="fold-hint">click an account to see why and what to do</span></>}>
        <div className="verdict-grid">
          {c.accounts.map((a) => <AccountCard key={a.account_id} a={a} />)}
        </div>
      </Fold>

      <Fold title={`Mule rings (${c.rings.length})`}>
          {c.rings.length === 0 ? <p className="muted">No ring of accounts sharing counterparties was found.</p> : (
            <table>
              <thead><tr><th>Ring</th><th>Accounts</th><th className="num">Shared counterparties</th><th className="num">Money through ring</th><th className="num">Top risk</th></tr></thead>
              <tbody>
                {c.rings.map((r) => (
                  <tr key={r.ring_id}>
                    <td><Link to={`/network/${r.ring_id}`}>{r.ring_id}</Link></td>
                    <td>{r.accounts.map((a, i) => <span key={a}>{i > 0 && ", "}<Link to={`/accounts/${a}`}>{a}</Link></span>)}</td>
                    <td className="num">{num(r.n_shared_counterparties)}</td>
                    <td className="num">{inrShort(r.total_amount)}</td>
                    <td className="num">{score(r.max_risk)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </Fold>
      <div className="fold-row">
      <Fold title={`Largest account-to-account chains (${c.top_chains.length})`}>
          {c.top_chains.length === 0 ? <p className="muted">No chain carries money from one investigated account to another.</p> : (
            <ol className="chain-list">
              {c.top_chains.map((ch) => (
                <li key={ch.nodes.join(">")}>
                  <div className="chain-row">
                    {ch.labels.map((l, i) => (
                      <span key={i} className="chain-node-wrap">
                        {i > 0 && <span className="arrow"> → </span>}
                        <span className={ch.nodes[i].startsWith("SOA") ? "chain-node subj" : "chain-node cp"}>{l}</span>
                      </span>
                    ))}
                  </div>
                  <div className="small muted">
                    {inr(ch.amount)} end to end · {ch.hops} hops · <Link to={`/trail/${ch.start}`}>see on the money trail →</Link>
                  </div>
                </li>
              ))}
            </ol>
          )}
      </Fold>

      {c.watchlist.length > 0 && (
        <Fold title={`Watchlist (${c.watchlist.length})`}>
          <table>
            <thead><tr><th>Account</th><th className="num">Risk</th><th>Role</th><th className="num">Unusual weeks</th><th>Why it is watched</th></tr></thead>
            <tbody>
              {c.watchlist.map((a) => (
                <tr key={a.account_id}>
                  <td><Link to={`/accounts/${a.account_id}`}>{a.account_id}</Link></td>
                  <td className="num">{score(a.risk_score)}</td>
                  <td><RoleBadge role={a.role} /></td>
                  <td className="num">{a.flagged_weeks ?? "—"}</td>
                  <td className="small">{a.reasons[0] ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Fold>
      )}
      </div>

      <h2>Overview</h2>
      <div className="findings">
        {c.findings.map((f) => (
          <Link key={f.tab} to={f.route} className="finding">
            <span className="finding-tab">{f.tab}</span>
            <b>{f.title}</b>
            <p>{f.text}</p>
            <span className="finding-open">Open {f.tab} →</span>
          </Link>
        ))}
      </div>

      <div className="fold-row">
      <Fold title="Recommended next steps">
        <ol className="steps-list">{c.next_steps.map((s) => <li key={s}>{s}</li>)}</ol>
      </Fold>
      <Fold title="How far to trust this">
        <ul className="limits-list">{c.limitations.map((s) => <li key={s}>{s}</li>)}</ul>
      </Fold>
      </div>
    </>
  );
}

export function Overview() {
  const conclusion = useConclusion();
  const stats = useStats();
  const [running, setRunning] = useState(false);
  const [runMsg, setRunMsg] = useState<string>();

  const rerun = async () => {
    setRunning(true);
    setRunMsg(undefined);
    try {
      const r = await api.runPipeline();
      setRunMsg(`Pipeline finished: ${num(r.stats.n_transactions)} transactions, ${r.stats.n_alerts} alerts.`);
      stats.reload();
      conclusion.reload();
    } catch (e) {
      setRunMsg(`Pipeline failed: ${(e as Error).message}`);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div>
      <h1>Dashboard</h1>
      <Async state={conclusion} what="the conclusion">
        {(c) => (
          <ConclusionView
            c={c}
            glance={
              <Async state={stats} what="statistics">
                {(s) => (
                  <>
                    <div className="tiles tiles-row">
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
            }
          />
        )}
      </Async>

      <Fold title="How Trace360 works">
        <div className="stages">
          {STAGES.map(([t, d]) => (
            <div className="stage" key={t}><b>{t}</b><p>{d}</p></div>
          ))}
        </div>
      </Fold>
      <p className="muted">Leads are prompts for investigation, not proof. There are no fraud labels in the data, so model quality is measured with a synthetic test. See <Link to="/models">Models</Link>.</p>
    </div>
  );
}
