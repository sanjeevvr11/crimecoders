import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import type { TrailChain, TrailDirection, TrailGraph, TrailGraphNode } from "../api/types";
import { Async, RoleBadge, TierBadge, TrailGraphView, day, inr, inrShort, num } from "../components";
import type { TrailSelection } from "../components";
import { useLeads, useTrailGraph } from "../hooks";

const KIND_LABEL: Record<string, string> = {
  subject: "Investigated account", upi: "UPI ID", ifsc: "Bank branch (IFSC)", account: "Bank account", name: "Named payee", other: "Counterparty",
};
const CHAIN_LABEL: Record<string, string> = {
  "cross-account": "Reaches another investigated account",
  shared: "Common counterparty with another investigated account",
  exit: "Leaves the investigated set",
};

/** Money trail investigation view: where money came from, where it went, and the chains linking mule accounts. */
export function MoneyTrail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const leads = useLeads();
  const start = id ?? leads.data?.[0]?.account_id;
  const [direction, setDirection] = useState<TrailDirection>("both");
  const [hops, setHops] = useState(3);
  const trail = useTrailGraph(start, hops, direction);
  const [chainIdx, setChainIdx] = useState<number | null>(null);
  const [selection, setSelection] = useState<TrailSelection>(null);

  const go = (acc: string) => {
    setChainIdx(null);
    setSelection(null);
    navigate(`/trail/${acc}`);
  };

  return (
    <div className="trail-page">
      <div className="trail-head">
        <div>
          <div className="trail-kicker">MONEY TRAIL INVESTIGATION</div>
          <h1>Where did the money come from, and where did it go?</h1>
        </div>
        <div className="trail-controls">
          <label>Account{" "}
            <select value={start ?? ""} onChange={(e) => go(e.target.value)}>
              {(leads.data ?? []).map((l) => (
                <option key={l.account_id} value={l.account_id}>
                  {l.account_id} · {l.risk_score.toFixed(0)} {l.tier}{l.network_score === 0 ? " · no counterparties" : ""}
                </option>
              ))}
            </select>
          </label>
          <label>Follow{" "}
            <select value={direction} onChange={(e) => { setChainIdx(null); setDirection(e.target.value as TrailDirection); }}>
              <option value="both">both ways</option>
              <option value="backward">money in (sources)</option>
              <option value="forward">money out (destinations)</option>
            </select>
          </label>
          <label>Hops{" "}
            <select value={hops} onChange={(e) => { setChainIdx(null); setHops(Number(e.target.value)); }}>
              {[1, 2, 3, 4].map((h) => <option key={h}>{h}</option>)}
            </select>
          </label>
        </div>
      </div>

      <Async state={trail} what="money trail" isEmpty={(t) => t.edges.length === 0}
        empty={<>No counterparties are recorded for {start}: its narrations are opaque tokens, so money cannot be followed
          beyond the account. Pick an account from the list (those marked "no counterparties" have no trail).</>}>
        {(t) => (
          <TrailBody t={t} chainIdx={chainIdx} setChainIdx={setChainIdx} selection={selection}
            setSelection={(s) => { setChainIdx(null); setSelection(s); }} go={go} />
        )}
      </Async>
    </div>
  );
}

function TrailBody({ t, chainIdx, setChainIdx, selection, setSelection, go }: {
  t: TrailGraph;
  chainIdx: number | null;
  setChainIdx: (i: number | null) => void;
  selection: TrailSelection;
  setSelection: (s: TrailSelection) => void;
  go: (acc: string) => void;
}) {
  const byRef = useMemo(() => new Map(t.nodes.map((n) => [n.ref, n])), [t]);
  const startNode = t.nodes.find((n) => n.is_start)!;
  const chain = chainIdx == null ? null : t.chains[chainIdx];
  const s = t.summary;
  const shown = t.chains.slice(0, 25);
  return (
    <>
      <div className="trail-stats">
        <Stat label="Traced in" value={inrShort(s.amount_in)} hint="into the account along the trail" />
        <Stat label="Traced out" value={inrShort(s.amount_out)} hint="out of the account along the trail" />
        <Stat label="Intermediaries" value={num(s.n_intermediaries)} hint="received and passed money on" />
        <Stat label="Cross-account chains" value={num(s.n_cross_account_chains)} hint="reach another investigated account" />
        <Stat label="Circular flows" value={num(s.n_circular)} hint="money goes both to and from these" />
        <Stat label="Shared counterparties" value={num(s.n_shared_counterparties)} hint="also deal with other mule accounts" />
        <Stat label="Period" value={s.first_ts ? `${day(s.first_ts)} → ${day(s.last_ts)}` : "dates unreliable"} hint={s.time_reliable ? "timestamps reliable" : "statement dates are shuffled"} />
      </div>

      <div className="trail-main">
        <aside className="trail-card">
          <div className="trail-badge">UNDER INVESTIGATION</div>
          <div className="trail-title">{startNode.label}</div>
          <div><TierBadge tier={startNode.tier} /> <RoleBadge role={startNode.role} /></div>
          <dl>
            <dt>Risk score</dt><dd>{startNode.risk_score?.toFixed(1)}</dd>
            <dt>Ring</dt><dd>{startNode.ring_id ? <Link to={`/network/${startNode.ring_id}`}>{startNode.ring_id}</Link> : "none"}</dd>
            <dt>Linked accounts</dt>
            <dd>{s.accounts_reached.length ? s.accounts_reached.map((a) => (
              <button key={a} className="trail-chip" onClick={() => go(a)}>{a}</button>
            )) : "none found"}</dd>
          </dl>
          <Link to={`/accounts/${startNode.ref}`}>Open account details →</Link>
          <div className="trail-legend">
            <div><span className="lg-line" /> transfer (thicker = more money, dashes move with the money)</div>
            <div><span className="lg-line shared" /> common counterparty with another mule account</div>
            <div><span className="lg-node subject" /> investigated account (ring colour = risk tier)</div>
            <div><span className="lg-node circular" /> double ring: circular flow, money goes both to and from it</div>
            <div><span className="lg-node upi" /> UPI ID <span className="lg-node ifsc" /> bank branch <span className="lg-node name" /> payee</div>
          </div>
        </aside>

        <div className="trail-graph-wrap">
          <TrailGraphView graph={t} chain={chain} selection={selection} onSelect={setSelection} />
        </div>

        <aside className="trail-side">
          {selection ? <SelectionPanel t={t} sel={selection} byRef={byRef} go={go} onClose={() => setSelection(null)} /> : (
            <>
              <h3>Suspicious chains</h3>
              <p className="trail-muted">Click a chain to light it up on the graph, hop by hop.</p>
              <ol className="trail-chains">
                {shown.map((c, i) => (
                  <li key={i} className={chainIdx === i ? "active" : ""} onClick={() => setChainIdx(chainIdx === i ? null : i)}>
                    <span className={`chain-kind ${c.kind}`}>{c.kind}</span> <b>{inrShort(c.amount)}</b> · {c.hops} hop{c.hops > 1 ? "s" : ""}
                    <div className="chain-path">{chainLabel(c, byRef)}</div>
                  </li>
                ))}
              </ol>
              {t.chains.length > shown.length && <p className="trail-muted">+{t.chains.length - shown.length} more chains</p>}
            </>
          )}
        </aside>
      </div>

      {chain && <ChainSteps chain={chain} t={t} byRef={byRef} />}
    </>
  );
}

const Stat = ({ label, value, hint }: { label: string; value: string; hint: string }) => (
  <div className="trail-stat"><div className="v">{value}</div><div className="l">{label}</div><div className="h">{hint}</div></div>
);

function chainLabel(c: TrailChain, byRef: Map<string, TrailGraphNode>) {
  const names = c.nodes.map((r) => byRef.get(r)?.label ?? r);
  if (c.kind === "shared") {
    const [a, cp, b] = names;
    return c.direction === "backward" ? `${cp} paid both ${a} and ${b}` : `${a} and ${b} both paid ${cp}`;
  }
  return c.direction === "backward" ? [...names].reverse().join("  →  ") : names.join("  →  ");
}

/** The selected chain as steps in the order money moved, with the amount and dates of each hop. */
function ChainSteps({ chain, t, byRef }: { chain: TrailChain; t: TrailGraph; byRef: Map<string, TrailGraphNode> }) {
  const edge = (a: string, b: string) => t.edges.find((e) => (e.source === a && e.target === b) || (e.source === b && e.target === a));
  if (chain.kind === "shared") return <SharedSteps chain={chain} byRef={byRef} edge={edge} />;
  const order = chain.direction === "backward" ? [...chain.nodes].reverse() : chain.nodes;
  return (
    <section className="trail-steps">
      <h3>{CHAIN_LABEL[chain.kind]}</h3>
      <div className="steps">
        {order.map((ref, i) => {
          const n = byRef.get(ref);
          const e = i > 0 ? edge(order[i - 1], ref) : undefined;
          return (
            <div key={i} className="step-wrap">
              {e && (
                <div className="hop">
                  <div className="amt">{inr(e.amount)}</div>
                  <div className="arrow-line" />
                  <div className="meta">{e.count} txn{e.count > 1 ? "s" : ""} · {day(e.first_ts)}{e.last_ts && e.last_ts !== e.first_ts ? ` → ${day(e.last_ts)}` : ""}</div>
                </div>
              )}
              <div className={`step ${n?.is_subject ? "subject" : ""} ${n?.is_start ? "start" : ""}`}>
                <div className="k">{KIND_LABEL[n?.kind ?? "other"]}</div>
                <div className="n">{n?.label ?? ref}</div>
                {n?.is_subject && <div className="k">score {n.risk_score?.toFixed(0)} · {n.tier}</div>}
              </div>
            </div>
          );
        })}
      </div>
      <p className="trail-muted">The chain amount ({inr(chain.amount)}) is its smallest hop: at most that much can have moved end to end.
        {chain.first_ts ? "" : " Dates are not shown because this statement's timestamps are unreliable."}</p>
    </section>
  );
}

/** A common counterparty: one payer funding two investigated accounts, or one payee both pay. */
function SharedSteps({ chain, byRef, edge }: {
  chain: TrailChain;
  byRef: Map<string, TrailGraphNode>;
  edge: (a: string, b: string) => TrailGraph["edges"][number] | undefined;
}) {
  const [start, cp, other] = chain.nodes;
  const payer = chain.direction === "backward";
  const box = (ref: string) => {
    const n = byRef.get(ref);
    return (
      <div className={`step ${n?.is_subject ? "subject" : ""} ${n?.is_start ? "start" : ""}`}>
        <div className="k">{KIND_LABEL[n?.kind ?? "other"]}</div>
        <div className="n">{n?.label ?? ref}</div>
        {n?.is_subject && <div className="k">score {n.risk_score?.toFixed(0)} · {n.tier}</div>}
      </div>
    );
  };
  const hop = (a: string, b: string) => {
    const e = edge(a, b);
    return (
      <div className="hop">
        <div className="amt">{inr(e?.amount)}</div>
        <div className="arrow-line" />
        <div className="meta">{e?.count} txn{e?.count === 1 ? "" : "s"} · {day(e?.first_ts)}</div>
      </div>
    );
  };
  return (
    <section className="trail-steps">
      <h3>{CHAIN_LABEL.shared}</h3>
      {[start, other].map((acc) => (
        <div key={acc} className="steps">
          {payer ? <>{box(cp)}{hop(cp, acc)}{box(acc)}</> : <>{box(acc)}{hop(acc, cp)}{box(cp)}</>}
        </div>
      ))}
      <p className="trail-muted">{payer
        ? "The same sender paid money into both investigated accounts: a typical sign of one victim or one controller feeding several mule accounts."
        : "Both investigated accounts paid the same receiver: a typical sign of mule accounts draining into one collection point."}</p>
    </section>
  );
}

function SelectionPanel({ t, sel, byRef, go, onClose }: {
  t: TrailGraph;
  sel: NonNullable<TrailSelection>;
  byRef: Map<string, TrailGraphNode>;
  go: (acc: string) => void;
  onClose: () => void;
}) {
  if (sel.type === "edge") {
    const e = t.edges.find((x) => x.source === sel.source && x.target === sel.target);
    if (!e) return null;
    return (
      <div>
        <button className="link" onClick={onClose}>← chains</button>
        <h3>Transfer</h3>
        <p className="big">{byRef.get(e.source)?.label} → {byRef.get(e.target)?.label}</p>
        <dl>
          <dt>Amount</dt><dd>{inr(e.amount)}</dd>
          <dt>Transactions</dt><dd>{num(e.count)}</dd>
          <dt>First / last</dt><dd>{day(e.first_ts)} / {day(e.last_ts)}</dd>
          <dt>Hop</dt><dd>{e.hop} {e.direction === "backward" ? "back" : "on"} from {t.start}</dd>
          <dt>Link</dt><dd>{e.link === "shared" ? "common counterparty" : "traced transfer"}</dd>
        </dl>
      </div>
    );
  }
  const n = byRef.get(sel.ref);
  if (!n) return null;
  return (
    <div>
      <button className="link" onClick={onClose}>← chains</button>
      <h3>{KIND_LABEL[n.kind]}</h3>
      <p className="big">{n.label}</p>
      <dl>
        {n.is_subject && <><dt>Risk</dt><dd>{n.risk_score?.toFixed(1)} <TierBadge tier={n.tier} /></dd></>}
        {n.is_subject && <><dt>Role</dt><dd><RoleBadge role={n.role} /></dd></>}
        {n.bank && <><dt>Bank code</dt><dd>{n.bank}</dd></>}
        <dt>Position</dt><dd>{n.level === 0 ? (n.is_start ? "start" : "linked account") : `${Math.abs(n.level)} hop${Math.abs(n.level) > 1 ? "s" : ""} ${n.level < 0 ? "back (source)" : "on (destination)"}`}</dd>
        <dt>Money in</dt><dd>{inr(n.amount_in)}</dd>
        <dt>Money out</dt><dd>{inr(n.amount_out)}</dd>
        {n.circular && <><dt>Circular</dt><dd>money flows both to and from {t.start} through it</dd></>}
        <dt>Deals with</dt><dd>{n.n_subject_links} investigated account{n.n_subject_links === 1 ? "" : "s"}</dd>
      </dl>
      {n.is_subject && !n.is_start && <button onClick={() => go(n.ref)}>Trace from {n.ref}</button>}{" "}
      {n.is_subject && <Link to={`/accounts/${n.ref}`}>Account details →</Link>}
    </div>
  );
}
