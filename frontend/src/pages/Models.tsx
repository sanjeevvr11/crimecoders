import { Link } from "react-router-dom";
import { Async, RoleBadge } from "../components";
import { useModelSummary } from "../hooks";

// The evaluation block is free-form JSON in the contract; these are the fields this page reads.
type MS = { mean: number; std: number };
interface Evaluation {
  note: string;
  contamination: number;
  injection: Record<string, MS> & { recall_by_pattern: Record<string, MS> };
  contamination_sweep: Record<string, Record<string, MS>>;
  stability: {
    flagged_jaccard_across_seeds: MS;
    account_rank_spearman_across_seeds: MS;
    per_account_time_split: Record<string, number>;
    time_split: Record<string, number | string>;
  };
  agreement_with_rules: { accounts: number; spearman: number | null; p_value?: number };
  clustering: { chosen: Record<string, unknown>; alternative_eom: Record<string, unknown> };
}

const ms = (m?: MS) => (m ? `${m.mean.toFixed(3)} ± ${m.std.toFixed(3)}` : "—");

const MODELS = [
  ["Isolation Forest", "Flags the most unusual 5% of account-weeks, compared with all weeks and with the account's own usual week. Adds an uplift to the risk score.", "Unsupervised: no fraud labels exist."],
  ["SHAP TreeExplainer", "Explains each flagged week in plain English (which features made it unusual).", "Makes the model auditable."],
  ["HDBSCAN", "Groups weeks with similar behaviour and names each group: collector, distributor, layering, normal-looking. Outliers stay unclassified.", "Finds the number of groups itself; does not force outliers into a group."],
];

export function Models() {
  const summary = useModelSummary();
  return (
    <div className="models-page">
      <h1>Models</h1>
      <table>
        <thead><tr><th>Model</th><th>Use in Trace360</th><th>Why</th></tr></thead>
        <tbody>{MODELS.map(([m, u, w]) => <tr key={m}><td><b>{m}</b></td><td>{u}</td><td className="small">{w}</td></tr>)}</tbody>
      </table>
      <Async state={summary} what="model summary">
        {(s) => {
          const ev = s.evaluation as unknown as Evaluation | null;
          const card = s.model_card as Record<string, any>;
          return (
            <>
              <h2>Evaluation</h2>
              {!ev ? <p className="muted">No evaluation yet. Run <code>make train</code>.</p> : (
                <>
                  <p className="warning"><b>Not accuracy.</b> {ev.note}</p>
                  <h3>Synthetic injection test (mean ± std over 5 seeds)</h3>
                  <table>
                    <tbody>
                      <tr><td>ROC-AUC (0.5 = random)</td><td className="num">{ms(ev.injection.roc_auc)}</td></tr>
                      <tr><td>PR-AUC (random ≈ 0.10)</td><td className="num">{ms(ev.injection.pr_auc)}</td></tr>
                      <tr><td>Recall at the {(ev.contamination * 100).toFixed(0)}% flag rate</td><td className="num">{ms(ev.injection.recall_at_threshold)}</td></tr>
                      <tr><td>Precision at the flag rate</td><td className="num">{ms(ev.injection.precision_at_threshold)}</td></tr>
                      <tr><td>False alarms on clean weeks</td><td className="num">{ms(ev.injection.false_positive_rate)}</td></tr>
                    </tbody>
                  </table>
                  <h3>Recall by injected mule pattern</h3>
                  <table><tbody>{Object.entries(ev.injection.recall_by_pattern).map(([p, v]) => <tr key={p}><td>{p.replace(/_/g, " ")}</td><td className="num">{ms(v)}</td></tr>)}</tbody></table>
                  <h3>Stability and agreement</h3>
                  <table>
                    <tbody>
                      <tr><td>Flagged-week overlap across seeds (Jaccard)</td><td className="num">{ms(ev.stability.flagged_jaccard_across_seeds)}</td></tr>
                      <tr><td>Account ranking across seeds (Spearman)</td><td className="num">{ms(ev.stability.account_rank_spearman_across_seeds)}</td></tr>
                      <tr><td>Later weeks flagged by a model trained on earlier weeks (expect ~5%)</td><td className="num">{(ev.stability.per_account_time_split.flagged_share_early_model * 100).toFixed(0)}%</td></tr>
                      <tr><td>Agreement with rule indicators (Spearman, {ev.agreement_with_rules.accounts} accounts)</td><td className="num">{ev.agreement_with_rules.spearman}</td></tr>
                      <tr><td>HDBSCAN clusters / noise / DBCV</td><td className="num">{String(ev.clustering.chosen.clusters)} / {String(ev.clustering.chosen.noise_share)} / {String(ev.clustering.chosen.dbcv)}</td></tr>
                    </tbody>
                  </table>
                  <p className="muted">Full report: reports/model_evaluation.md in the repository.</p>
                </>
              )}

              <h2>Behaviour roles (HDBSCAN clusters)</h2>
              <table>
                <thead><tr><th>Cluster</th><th>Role</th><th className="num">Weeks</th><th className="num">Accounts</th><th className="num">Credit share</th><th className="num">Pass-through</th><th className="num">Fast outflow</th><th className="num">Dwell (h)</th></tr></thead>
                <tbody>
                  {s.role_profiles.map((p: Record<string, any>) => (
                    <tr key={p.cluster}>
                      <td>{p.cluster}</td><td><RoleBadge role={p.role} /></td><td className="num">{p.size}</td><td className="num">{p.n_accounts}</td>
                      <td className="num">{Number(p.cr_count_share).toFixed(2)}</td><td className="num">{Number(p.pass_through).toFixed(2)}</td>
                      <td className="num">{Number(p.fast_outflow_share).toFixed(2)}</td><td className="num">{Number(p.median_dwell_hours).toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <h3>Role per account</h3>
              <p>{s.account_roles.map((r: Record<string, any>) => (
                <span key={r.account_id} className="chip"><Link to={`/accounts/${r.account_id}`}>{r.account_id}</Link> <RoleBadge role={r.role} /></span>
              ))}</p>

              <h2>Model card</h2>
              <p className="muted">Trained {card.generated_at} on {card.training_data?.windows} account-weeks from {card.training_data?.accounts} accounts · scikit-learn {card.versions?.["scikit-learn"]} · SHAP {card.versions?.shap}</p>
              <details><summary>Raw model card JSON</summary><pre>{JSON.stringify(card, null, 2)}</pre></details>
            </>
          );
        }}
      </Async>
    </div>
  );
}
