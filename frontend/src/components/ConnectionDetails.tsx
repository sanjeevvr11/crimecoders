import { Link } from "react-router-dom";
import type { NodeConnections } from "../api/types";
import { ringColor } from "./RingGraph";
import { inr, num } from "./format";

const RingTag = ({ ringId }: { ringId?: string | null }) =>
  ringId ? <span className="badge" style={{ background: ringColor(ringId), color: "white" }}>{ringId}</span> : <span className="badge">no ring</span>;

/**
 * What a clicked graph node (or link) stands for: the accounts on the other end
 * and the transactions behind it. Paging and sort are owned by the caller.
 */
export function ConnectionDetails({ data, onAccount, onClearAccount, children }: {
  data: NodeConnections;
  /** narrow to one account (a row of the accounts table was clicked) */
  onAccount?: (accountId: string) => void;
  onClearAccount?: () => void;
  /** paging / sort controls */
  children?: React.ReactNode;
}) {
  const subject = data.is_subject;
  return (
    <div className="panel">
      <h3>
        {subject ? <Link to={`/accounts/${data.node.ref}`}>{data.node.label}</Link> : <span className="cp">{data.node.label}</span>}{" "}
        {subject ? <RingTag ringId={data.ring_id} /> : <span className="muted small">counterparty</span>}
        {data.account && <> ↔ <Link to={`/accounts/${data.account}`}>{data.account}</Link>{" "}
          {onClearAccount && <button className="link" onClick={onClearAccount}>show all links</button>}</>}
      </h3>
      {data.accounts.length === 0 ? (
        <p className="muted">{subject ? "This account shares no counterparty with another investigated account." : "No transactions."}</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>{subject ? "Shares counterparties with" : "Investigated account"}</th><th>Ring</th>
              {subject && <th className="num">Shared counterparties</th>}
              <th className="num">Transactions</th>
              <th className="num">{subject ? `${data.node.label} received` : "Received from it"}</th>
              <th className="num">{subject ? `${data.node.label} paid` : "Paid to it"}</th>
            </tr>
          </thead>
          <tbody>
            {data.accounts.map((a) => (
              <tr key={a.account_id} className={onAccount ? "clickable" : ""} onClick={() => onAccount?.(a.account_id)}>
                <td><Link to={`/accounts/${a.account_id}`} onClick={(e) => e.stopPropagation()}>{a.account_id}</Link></td>
                <td><RingTag ringId={a.ring_id} /></td>
                {subject && <td className="num">{num(a.n_shared_counterparties)}</td>}
                <td className="num">{num(a.n_txns)}</td>
                <td className="num">{inr(a.cr_amount)}</td>
                <td className="num">{inr(a.dr_amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {subject && data.accounts.length > 0 && (
        <p className="muted small">Amounts are {data.node.label}'s own transactions with the counterparties it shares with each account. Click a row to list only those.</p>
      )}
      {data.total > 0 && (
        <>
          <h4>Transactions</h4>
          {children}
          {data.transactions.some((x) => !x.txn_ts) && (
            <p className="muted small">Rows marked (raw) come from statements with shuffled dates, so their place in this order is not the real order of events.</p>
          )}
          <table>
            <thead><tr><th>Time</th><th>Account</th><th>Dir</th><th className="num">Amount</th><th>Channel</th><th>Counterparty</th><th>Narration</th></tr></thead>
            <tbody>
              {data.transactions.map((x) => (
                <tr key={x.txn_uid}>
                  <td className="small">{x.txn_ts?.replace("T", " ") ?? <span className="muted">{x.raw_date} (raw)</span>}</td>
                  <td><Link to={`/accounts/${x.account_id}`}>{x.account_id}</Link></td>
                  <td className={x.direction === "CR" ? "cr" : "dr"}>{x.direction}</td>
                  <td className="num">{inr(x.amount)}</td>
                  <td>{x.channel}</td>
                  <td className="small cp">{x.counterparty?.label ?? "—"}</td>
                  <td className="small mono">{x.narration}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
