import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import {
  Async, DailyFlowChart, ReasonList, RoleBadge, TierBadge, TrailExplorer, WeeklyAnomalyChart, inr, num, pct, score,
} from "../components";
import type { SortOrder } from "../api";
import { useAccount, useAuth, useTimeline } from "../hooks";

const PAGE = 50;

export function Account() {
  const { id } = useParams();
  const account = useAccount(id);
  const [offset, setOffset] = useState(0);
  const [direction, setDirection] = useState<"" | "CR" | "DR">("");
  const [order, setOrder] = useState<SortOrder>("asc");
  const canSeeTransactions = useAuth().can("investigator"); // the API refuses transactions and PDFs to viewers
  const timeline = useTimeline(canSeeTransactions ? id : undefined, PAGE, offset, direction || undefined, order);

  return (
    <div>
      <p><Link to="/leads">← Leads</Link></p>
      <Async state={account} what="account">
        {(a) => (
          <>
            <h1>{a.account_id} <TierBadge tier={a.score.tier} /> <RoleBadge role={a.role} /></h1>
            <p className="muted">
              Holder {a.holder_name ?? "—"} · account {a.account_number ?? "anonymised per row"} · {a.source_file} ({a.layout}) ·{" "}
              {num(a.n_rows)} transactions · timestamps {a.time_reliable ? "reliable" : "not reliable (dates shuffled)"}
              {a.score.ring_id && <> · ring <Link to={`/network/${a.score.ring_id}`}>{a.score.ring_id}</Link></>}
            </p>
            {canSeeTransactions && <p><a className="button" href={api.reportUrl(a.account_id)} target="_blank" rel="noreferrer">Download evidence PDF</a></p>}

            <div className="grid2">
              <section>
                <h2>Score breakdown</h2>
                <table>
                  <tbody>
                    <tr><td>Rule indicators (0-1)</td><td className="num">{a.score.indicator_score.toFixed(3)}</td></tr>
                    <tr><td>Network (0-1)</td><td className="num">{a.score.network_score.toFixed(3)}</td></tr>
                    <tr><td>Base score = 65% rules + 35% network</td><td className="num">{score(a.score.base_score)}</td></tr>
                    <tr><td>Anomaly score (0-1)</td><td className="num">{a.anomaly_score == null ? "n/a (no reliable timestamps)" : a.anomaly_score.toFixed(3)}</td></tr>
                    <tr><td>Anomaly uplift</td><td className="num">+{score(a.score.anomaly_uplift)}</td></tr>
                    <tr className="total"><td>Risk score (rank {a.score.rank})</td><td className="num">{score(a.score.risk_score)}</td></tr>
                    <tr><td className="muted">Phase 1 score (rules + network)</td><td className="num muted">{score(a.score.risk_score_phase1)}</td></tr>
                  </tbody>
                </table>
              </section>
              <section>
                <h2>Why it was flagged</h2>
                <ReasonList reasons={a.reasons} />
                <p className="muted">Role: <RoleBadge role={a.role} /> {a.role_source && `(from ${a.role_source})`} · flagged weeks: {a.flagged_weeks ?? "n/a"} · complaint matches: {a.complaint_matches}</p>
              </section>
            </div>

            <h2>Unusual weeks (Isolation Forest + SHAP)</h2>
            {a.shap_reasons.length === 0 ? (
              <p className="muted">{a.time_reliable ? "No week of this account is in the most unusual 5%." : "Not available: this statement has no reliable timestamps."}</p>
            ) : (
              <table>
                <thead><tr><th>Week of</th><th className="num">Score</th><th>Most unusual</th><th>Why (SHAP)</th></tr></thead>
                <tbody>
                  {a.shap_reasons.map((w) => (
                    <tr key={w.week_start}>
                      <td>{w.week_start}</td>
                      <td className="num">{w.anomaly_score.toFixed(2)}</td>
                      <td>top {Math.max(1, Math.round((1 - w.percentile) * 100))}%</td>
                      <td><ul className="tight">{w.reasons.map((r) => <li key={r.feature}>{r.text}</li>)}</ul></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <h2>Rule indicators</h2>
            <table>
              <thead><tr><th>Indicator</th><th className="num">Value</th><th className="num">Sub-score</th><th className="num">Weight</th><th>Reason</th></tr></thead>
              <tbody>
                {a.indicators.map((i) => (
                  <tr key={i.indicator}>
                    <td>{i.indicator}</td><td className="num">{num(i.value, 3)}</td><td className="num">{pct(i.subscore)}</td>
                    <td className="num">{i.weight}</td><td className="small">{i.reason ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </Async>

      <h2>Timeline</h2>
      {!canSeeTransactions ? <p className="muted role-note">Transactions and the evidence PDF need the investigator or admin role.</p> : <Async state={timeline} what="timeline">
        {(t) => (
          <>
            {(t.weeks ?? []).length > 0 && (<><h3>Weekly anomaly score <span className="muted">(red = flagged)</span></h3><WeeklyAnomalyChart weeks={t.weeks ?? []} /></>)}
            {t.daily.length > 0 ? (<><h3>Daily credits and debits</h3><DailyFlowChart daily={t.daily} /></>)
              : <p className="muted">Dates in this statement are shuffled, so no time chart is shown.</p>}
            <h3>Transactions</h3>
            <div className="controls">
              <label>Direction <select value={direction} onChange={(e) => { setDirection(e.target.value as "" | "CR" | "DR"); setOffset(0); }}>
                <option value="">all</option><option value="CR">credits</option><option value="DR">debits</option>
              </select></label>
              <label>Date <select value={order} onChange={(e) => { setOrder(e.target.value as SortOrder); setOffset(0); }}>
                <option value="asc">oldest first</option><option value="desc">newest first</option>
              </select></label>
              <span>{num(offset + 1)}–{num(Math.min(offset + PAGE, t.total))} of {num(t.total)}</span>
              <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
              <button disabled={offset + PAGE >= t.total} onClick={() => setOffset(offset + PAGE)}>Next</button>
            </div>
            {!t.time_reliable && <p className="muted small">Sorted by the raw dates, which are shuffled in this statement, so this is not the real order of events.</p>}
            <table>
              <thead><tr><th>Time</th><th>Dir</th><th className="num">Amount</th><th>Channel</th><th>Counterparty</th><th>Narration</th></tr></thead>
              <tbody>
                {t.transactions.map((x) => (
                  <tr key={x.txn_uid}>
                    <td className="small">{x.txn_ts?.replace("T", " ") ?? <span className="muted">{x.raw_date} (raw)</span>}</td>
                    <td className={x.direction === "CR" ? "cr" : "dr"}>{x.direction}</td>
                    <td className="num">{inr(x.amount)}</td>
                    <td>{x.channel}</td>
                    <td className="small">{x.counterparty?.label ?? "—"}</td>
                    <td className="small mono">{x.narration}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </Async>}

      <h2>Money trail</h2>
      {id && <p><Link className="button" to={`/trail/${id}`}>Open the Money Trail investigation view →</Link></p>}
      {id && <TrailExplorer accountId={id} />}
    </div>
  );
}
