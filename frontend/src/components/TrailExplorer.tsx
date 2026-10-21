import { useState } from "react";
import { Link } from "react-router-dom";
import type { TrailDirection } from "../api/types";
import { useTrail } from "../hooks";
import { Async } from "./Status";
import { inr } from "./format";

/** Hop-limited money trail from an account, forward (where money went) or backward (where it came from). */
export function TrailExplorer({ accountId }: { accountId: string }) {
  const [hops, setHops] = useState(2);
  const [direction, setDirection] = useState<TrailDirection>("forward");
  const trail = useTrail(accountId, hops, direction, 50);
  return (
    <div>
      <div className="controls">
        <label>Direction{" "}
          <select value={direction} onChange={(e) => setDirection(e.target.value as TrailDirection)}>
            <option value="forward">forward (where money went)</option>
            <option value="backward">backward (where it came from)</option>
            <option value="both">both</option>
          </select>
        </label>
        <label>Hops{" "}
          <select value={hops} onChange={(e) => setHops(Number(e.target.value))}>
            {[1, 2, 3, 4].map((h) => <option key={h}>{h}</option>)}
          </select>
        </label>
      </div>
      <Async state={trail} what="money trail" isEmpty={(t) => t.paths.length === 0}
        empty="No counterparties recorded for this account (narrations are opaque tokens), so no trail can be followed.">
        {(t) => (
          <>
            <p className="muted">{t.paths.length} paths (largest flows first; time order respected where timestamps exist). Amount shown is the smallest hop on the path.</p>
            <table>
              <thead><tr><th>Hops</th><th>Path</th><th className="num">Amount</th></tr></thead>
              <tbody>
                {t.paths.map((p, i) => (
                  <tr key={i}>
                    <td>{p.hops}</td>
                    <td>
                      {p.nodes.map((n, j) => (
                        <span key={j}>
                          {j > 0 && <span className="arrow">{p.direction === "backward" ? " ← " : " → "}</span>}
                          {n.is_subject ? <Link to={`/accounts/${n.ref}`}><b>{n.label}</b></Link> : <span className="cp">{n.label}</span>}
                        </span>
                      ))}
                    </td>
                    <td className="num">{inr(p.total_amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </Async>
    </div>
  );
}
