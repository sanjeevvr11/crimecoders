import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { SortOrder } from "../api";
import {
  Async, ConnectionDetails, NO_RING_COLOR, RING_COLORS, RingGraph, inr, num, ringColor, type GraphSelection,
} from "../components";
import { useNetworkOverview, useNodeTransactions, useRing, useRings } from "../hooks";

const PAGE = 50;

export function Network() {
  const { ringId } = useParams(); // undefined = every account and every ring
  const rings = useRings();
  const overview = useNetworkOverview();
  const ring = useRing(ringId);

  const [sel, setSel] = useState<GraphSelection>();
  const [offset, setOffset] = useState(0);
  const [order, setOrder] = useState<SortOrder>("asc");
  const details = useNodeTransactions(sel?.ref, sel?.account, PAGE, offset, order);
  useEffect(() => setSel(undefined), [ringId]);
  const onSelect = useCallback((s: GraphSelection) => { setSel(s); setOffset(0); }, []);

  return (
    <div>
      <h1>Network</h1>
      <p className="muted">A ring is a group of investigated accounts that deal with many of the same outside people or accounts.</p>
      <Async state={rings} what="rings">
        {(list) => (
          <table>
            <thead><tr><th>View</th><th>Accounts</th><th className="num">Shared counterparties</th><th className="num">Links</th><th className="num">Flow</th></tr></thead>
            <tbody>
              <tr className={!ringId ? "selected" : ""}>
                <td><Link to="/network">All accounts</Link></td>
                <td className="muted">{overview.data ? `${overview.data.n_accounts} accounts, ${overview.data.n_unlinked_accounts} share no counterparty` : "every account"}</td>
                <td className="num">{overview.data && num(overview.data.elements.nodes.filter((n) => !n.data.is_subject).length)}</td>
                <td className="num">{overview.data && num(overview.data.elements.edges.length)}</td>
                <td className="num">{overview.data && inr(overview.data.elements.edges.reduce((s, e) => s + e.data.amount, 0))}</td>
              </tr>
              {list.map((r) => (
                <tr key={r.ring_id} className={r.ring_id === ringId ? "selected" : ""}>
                  <td><span className="swatch" style={{ background: ringColor(r.ring_id) }} /> <Link to={`/network/${r.ring_id}`}>Ring {r.ring_id}</Link></td>
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

      <h2>Graph</h2>
      <p className="muted">
        The graph shows {ringId ? `the accounts in ring ${ringId}` : "every investigated account"}; click any dot or line to see the transactions behind it.
      </p>
      {ringId
        ? <Async state={ring} what="ring graph">{(g) => <RingGraph elements={g.elements} onSelect={onSelect} height="calc(100vh - 140px)" />}</Async>
        : <Async state={overview} what="network graph">{(g) => <RingGraph elements={g.elements} onSelect={onSelect} height="calc(100vh - 140px)" />}</Async>}
      <p className="muted graph-help">Use + and − (or Ctrl / ⌘ + scroll, or pinch) to zoom, drag the background to move around,
        Fit to see everything again, and Full screen for more room.</p>
      <section className="legend-box">
        <h3>How to read the graph</h3>
        <div className="legend-grid">
          <div><span className="sym">{RING_COLORS.slice(0, 3).map((c) => <span key={c} className="lg-dot" style={{ width: 16, height: 16, background: c }} />)}</span>
            Large dot: investigated account, coloured by its ring (see the table above)</div>
          <div><span className="sym"><span className="lg-dot" style={{ width: 16, height: 16, background: NO_RING_COLOR }} /></span> Slate large dot: account in no ring</div>
          <div><span className="sym"><span className="lg-dot" style={{ width: 8, height: 8, background: "#5d6f8c" }} /></span> Small grey dot: outside counterparty shared by 2 accounts (masked)</div>
          <div><span className="sym"><span className="lg-dot" style={{ width: 10, height: 10, background: "#ffd166" }} /></span> Small gold dot: counterparty shared by 3 or more accounts</div>
          <div><span className="sym"><span className="lg-line plain" /></span> Line: the account sent money to or received money from that counterparty</div>
          <div><span className="sym"><span className="lg-line red" /></span> Pink: the dot or line you clicked and its links; everything else fades</div>
          <div><span className="sym"><span className="lg-dot" style={{ width: 8, height: 8, background: "#5d6f8c" }} /><span className="lg-dot" style={{ width: 8, height: 8, background: "#5d6f8c" }} /><span className="lg-dot" style={{ width: 8, height: 8, background: "#5d6f8c" }} /></span>
            A cluster of small dots between accounts = people or accounts they all deal with</div>
          {!ringId && <div><span className="sym"><span className="lg-dot" style={{ width: 16, height: 16, background: NO_RING_COLOR }} /><span className="lg-dot" style={{ width: 16, height: 16, background: NO_RING_COLOR }} /></span>
            Bottom row: accounts that share no counterparty with any other account</div>}
        </div>
      </section>

      <h2>Connection details</h2>
      {!sel ? <p className="muted">Click a dot or a line in the graph.</p> : (
        <Async state={details} what="transactions">
          {(d) => (
            <ConnectionDetails
              data={d}
              onAccount={(a) => { setSel({ ...sel, account: a }); setOffset(0); }}
              onClearAccount={() => { setSel({ ref: sel.ref, isSubject: sel.isSubject }); setOffset(0); }}
            >
              <div className="controls">
                <label>Date <select value={order} onChange={(e) => { setOrder(e.target.value as SortOrder); setOffset(0); }}>
                  <option value="asc">oldest first</option><option value="desc">newest first</option>
                </select></label>
                <span>{num(offset + 1)}–{num(Math.min(offset + PAGE, d.total))} of {num(d.total)}</span>
                <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
                <button disabled={offset + PAGE >= d.total} onClick={() => setOffset(offset + PAGE)}>Next</button>
              </div>
            </ConnectionDetails>
          )}
        </Async>
      )}
    </div>
  );
}
