import { useCallback } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Async, RingGraph, inr, num } from "../components";
import { useRing, useRings } from "../hooks";

export function Network() {
  const { ringId } = useParams();
  const navigate = useNavigate();
  const rings = useRings();
  const selected = ringId ?? rings.data?.[0]?.ring_id;
  const ring = useRing(selected);
  const onSelect = useCallback((id: string, isSubject: boolean) => {
    if (isSubject) navigate(`/accounts/${id}`);
  }, [navigate]);

  return (
    <div>
      <h1>Network</h1>
      <p className="muted">Rings are groups of investigated accounts that share many counterparties (Louvain communities on the money-flow graph).</p>
      <Async state={rings} what="rings" isEmpty={(r) => r.length === 0} empty="No rings found.">
        {(list) => (
          <table>
            <thead><tr><th>Ring</th><th>Accounts</th><th className="num">Shared counterparties</th><th className="num">Links</th><th className="num">Flow</th></tr></thead>
            <tbody>
              {list.map((r) => (
                <tr key={r.ring_id} className={r.ring_id === selected ? "selected" : ""}>
                  <td><Link to={`/network/${r.ring_id}`}>{r.ring_id}</Link></td>
                  <td>{r.subject_accounts.map((a, i) => <span key={a}>{i > 0 && ", "}<Link to={`/accounts/${a}`}>{a}</Link></span>)}</td>
                  <td className="num">{num(r.n_shared_counterparties)}</td>
                  <td className="num">{num(r.n_edges)}</td>
                  <td className="num">{inr(r.total_amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Async>
      {selected && (
        <>
          <h2>Ring {selected}</h2>
          <p className="muted">Dark nodes = investigated accounts (click to open). Gold = hub counterparties linked to 3+ nodes. Grey = other shared counterparties (masked).</p>
          <Async state={ring} what="ring graph">{(r) => <RingGraph elements={r.elements} onSelect={onSelect} />}</Async>
        </>
      )}
    </div>
  );
}
