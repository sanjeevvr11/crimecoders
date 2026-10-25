import { useState } from "react";
import { Link } from "react-router-dom";
import { Async, inr } from "../components";
import { useComplaintMatches, useComplaints } from "../hooks";

export function Complaints() {
  const complaints = useComplaints();
  const [selected, setSelected] = useState<string>();
  const matches = useComplaintMatches(selected);

  return (
    <div>
      <h1>Complaints</h1>
      <p className="muted">Each complaint's reported UPI ID or account is matched against the counterparties in the statements. Select a complaint to see what it matches.</p>
      <div className="complaints-stack">
        <section className="complaints-matches">
          <h2>Matches</h2>
          {!selected ? <p className="muted">Select a complaint to see which transactions, accounts and rings it matches.</p> : (
            <Async state={matches} what="matches">
              {(m) => (
                <>
                  <p>{m.complaint.complaint_id}: {m.complaint.victim} reported <span className="mono">{m.complaint.reported_upi_or_account}</span> for {inr(m.complaint.amount)} via {m.complaint.channel}.</p>
                  {m.matches.length === 0 ? <p className="muted">No match above the confidence threshold (expected for decoy complaints).</p> : (
                    <table>
                      <thead><tr><th>Counterparty</th><th>Account</th><th>Ring</th><th className="num">ID similarity</th><th>Amount ±2%</th><th>Date window</th><th className="num">Confidence</th></tr></thead>
                      <tbody>
                        {m.matches.map((x, i) => (
                          <tr key={i}>
                            <td className="mono small">{x.counterparty.label}</td>
                            <td><Link to={`/accounts/${x.account_id}`}>{x.account_id}</Link></td>
                            <td>{x.ring_id ? <Link to={`/network/${x.ring_id}`}>{x.ring_id}</Link> : "—"}</td>
                            <td className="num">{x.id_score.toFixed(0)}</td>
                            <td>{x.amount_match ? "yes" : "no"}</td>
                            <td>{x.time_match == null ? "n/a" : x.time_match ? "yes" : "no"}</td>
                            <td className="num"><b>{(x.confidence * 100).toFixed(0)}%</b></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </>
              )}
            </Async>
          )}
        </section>
        <section className="complaints-list">
          <h2>Complaints</h2>
          <div className="scroll-box">
            <Async state={complaints} what="complaints" isEmpty={(c) => c.length === 0} empty="No complaints.">
              {(list) => (
                <table>
                  <thead><tr><th>Complaint</th><th>Date</th><th>Reported ID</th><th className="num">Amount</th><th className="num">Best match</th></tr></thead>
                  <tbody>
                    {list.map((c) => (
                      <tr key={c.complaint_id} className={c.complaint_id === selected ? "selected clickable" : "clickable"} onClick={() => setSelected(c.complaint_id)}>
                        <td>{c.complaint_id}</td>
                        <td className="small">{c.date?.slice(0, 10)}</td>
                        <td className="mono small">{c.reported_upi_or_account} <span className="muted">({c.reported_type})</span></td>
                        <td className="num">{inr(c.amount)}</td>
                        <td className="num">{c.best_confidence == null
                          ? <span className="badge badge-nomatch">no match</span>
                          : <span className="badge badge-match">{c.best_account_id} · {(c.best_confidence * 100).toFixed(0)}%</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Async>
          </div>
        </section>
      </div>
    </div>
  );
}
