import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { DatasetState, PipelineJob, RunMode, StagedFile } from "../api/types";
import { Async, num } from "../components";
import { useDataset } from "../hooks";

const LAYOUTS: [string, string][] = [
  ["icore_short", "ICORE statement: Ac_No, Tran_Date, Dr_Amt, Cr_Amt, Narration, pstd_dt. Timestamps are reliable."],
  ["icore_full", "Full ICORE extract: Cust_ID, Tran_Type, Sub_Type, Dr_Amt, Cr_Amt, pstd_dt, value_dt. Timestamps are reliable."],
  ["crn_statement", "CRN statement: Account No, TXN DATE, AMOUNT, TXN PARTICULARS and a debit/credit flag column."],
  ["debit_credit", "Debit/credit sheet: Customer_Name, Date_of_transaction, Narration, Debit_amount, Credit_Amount."],
  ["misc_ledger", "Customer ledger: CUSTOMER ID, TRANSACTION DATE, NARRATION, DEBIT AMOUNT, CREDIT AMOUNT."],
  ["misc_wide", "Wide extract: TXN DATE, PSTD DATE, Dr Cr, AMOUNT, TXN PARTICULARS and account details."],
];

const STEP_LABEL: Record<string, string> = {
  ingest: "Reading statements", features: "Computing indicators", graph: "Building the money-flow graph",
  models: "Training the models", complaints: "Matching complaints", scoring: "Scoring accounts", write: "Saving results",
};

const size = (b: number) => (b >= 1 << 20 ? `${(b / (1 << 20)).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);
const when = (iso?: string | null) => (iso ? iso.replace("T", " ").slice(0, 16) : "—");

function JobPanel({ job }: { job: PipelineJob }) {
  if (job.state === "idle") return null;
  const pct = Math.round((100 * job.steps_done) / job.steps.length);
  if (job.state === "running") {
    const next = job.steps[job.steps_done];
    return (
      <div className="job running">
        <b>Analysing… {pct}%</b> <span className="muted">{next ? STEP_LABEL[next] ?? next : "Finishing"} (about a minute on the full data)</span>
        <div className="job-bar"><span style={{ width: `${Math.max(pct, 3)}%` }} /></div>
        <div className="job-steps">
          {job.steps.map((s, i) => <span key={s} className={i < job.steps_done ? "done" : i === job.steps_done ? "now" : ""}>{STEP_LABEL[s] ?? s}</span>)}
        </div>
      </div>
    );
  }
  if (job.state === "failed") {
    return (
      <div className="job failed">
        <b>The analysis failed.</b> The previous results are still shown on every screen. <span className="small mono">{job.error}</span>
      </div>
    );
  }
  return (
    <div className="job done">
      <b>Analysis finished {when(job.finished_at)}:</b> {num(job.n_transactions)} transactions, {job.n_accounts} accounts, {job.n_alerts} alerts.{" "}
      <Link to="/">See the conclusion on the Overview →</Link>
    </div>
  );
}

function SheetChecks({ f }: { f: StagedFile }) {
  return (
    <ul className="tight small">
      {f.sheets.map((s) => (
        <li key={s.sheet}>
          <span className="mono">{s.sheet}</span>: <b>{s.layout}</b>, {num(s.n_rows)} rows,{" "}
          {s.time_reliable ? <>dates {s.first_date} → {s.last_date}</> : <span className="muted">dates not reliable (time checks skipped)</span>},{" "}
          {s.pct_counterparty > 0 ? <>counterparties on {s.pct_counterparty}% of rows</> : <span className="muted">no counterparties (no money trail)</span>}
        </li>
      ))}
    </ul>
  );
}

type Rejected = { name: string; error: string };

function DataView({ d, reload, setJob }: { d: DatasetState; reload: () => void; setJob: (j: PipelineJob) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<RunMode>("add");
  const [uploading, setUploading] = useState<string[]>([]);
  const [rejected, setRejected] = useState<Rejected[]>([]);
  const [drag, setDrag] = useState(false);
  const [err, setErr] = useState<string>();
  const busy = d.job.state === "running";

  const act = async (fn: () => Promise<DatasetState | unknown>) => {
    setErr(undefined);
    try {
      const r = await fn();
      if (r && typeof r === "object" && "job" in r) setJob((r as DatasetState).job);
    } catch (e) {
      setErr((e as Error).message);
    }
    reload();
  };

  const upload = async (files: FileList | File[]) => {
    const list = Array.from(files);
    setUploading(list.map((f) => f.name));
    setRejected([]);
    setErr(undefined);
    const bad: Rejected[] = [];
    for (const f of list) {
      try {
        const r = await api.uploadStatement(f);
        if (!r.ok) bad.push({ name: f.name, error: r.error ?? "rejected" });
      } catch (e) {
        bad.push({ name: f.name, error: (e as Error).message });
      }
      setUploading((u) => u.filter((n) => n !== f.name));
    }
    setRejected(bad);
    reload();
  };

  const run = () => {
    const n = d.files.length;
    if (mode === "replace" && !window.confirm(`Replace the current ${n} statement${n === 1 ? "" : "s"} with the ${d.staged.length} uploaded file${d.staged.length === 1 ? "" : "s"}? The current statements are set aside and can be restored.`)) return;
    setRejected([]);
    act(() => api.runAnalysis(d.staged.length ? mode : "add"));
  };

  return (
    <>
      {d.needs_rerun && !busy && (
        <p className="warning">The statements changed since the results were computed. Run the analysis to update every screen.</p>
      )}
      <JobPanel job={d.job} />
      {err && <p className="status error">{err}</p>}

      <h2>1. Upload statements</h2>
      <div
        className={`dropzone${drag ? " over" : ""}${busy ? " disabled" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); if (!busy) upload(e.dataTransfer.files); }}
        onClick={() => !busy && input.current?.click()}
      >
        <b>Drop bank statements here</b> or click to choose files
        <div className="small muted">{d.accepted.join(", ")} · up to {d.max_upload_mb} MB each · every file is checked before it is used</div>
        <input ref={input} type="file" multiple hidden accept={d.accepted.join(",")}
          onChange={(e) => { if (e.target.files?.length) upload(e.target.files); e.target.value = ""; }} />
      </div>
      {uploading.length > 0 && <p className="muted">Checking {uploading.join(", ")}…</p>}
      {rejected.length > 0 && (
        <div className="status error">
          <b>Not added:</b>
          <ul className="tight">{rejected.map((r) => <li key={r.name}><b>{r.name}</b>: {r.error}</li>)}</ul>
        </div>
      )}

      <h2>2. Check and run the analysis</h2>
      {d.staged.length === 0 ? (
        <p className="muted">No uploads waiting. You can still re-run the analysis on the current statements.</p>
      ) : (
        <table>
          <thead><tr><th>Uploaded file</th><th className="num">Size</th><th>What Trace360 found</th><th /></tr></thead>
          <tbody>
            {d.staged.map((f) => (
              <tr key={f.id}>
                <td><b>{f.original_name}</b><div className="small muted">{when(f.uploaded_at)}</div></td>
                <td className="num">{size(f.size_bytes)}</td>
                <td><SheetChecks f={f} /></td>
                <td><button className="link" disabled={busy} onClick={() => act(() => api.removeUpload(f.id))}>remove</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="run-box">
        {d.staged.length > 0 && (
          <div className="mode">
            <label className={mode === "add" ? "on" : ""}>
              <input type="radio" name="mode" checked={mode === "add"} onChange={() => setMode("add")} />
              <b>Add to the current dataset</b>
              <span className="small muted">The uploads join the {d.files.length} current statements and everything is analysed together, so new accounts can link into existing rings.</span>
            </label>
            <label className={mode === "replace" ? "on" : ""}>
              <input type="radio" name="mode" checked={mode === "replace"} onChange={() => setMode("replace")} />
              <b>Replace the current dataset</b>
              <span className="small muted">Only the uploads are analysed. The current statements are set aside below and can be restored at any time.</span>
            </label>
          </div>
        )}
        <button onClick={run} disabled={busy}>
          {busy ? "Analysis running…" : d.staged.length ? `Run analysis (${mode === "add" ? "add" : "replace"})` : "Re-run analysis on the current statements"}
        </button>
      </div>

      <h2>Statements in the dataset ({d.files.length})</h2>
      <table>
        <thead><tr><th>File</th><th>Accounts</th><th>Layout</th><th className="num">Rows</th><th>Timestamps</th><th>Counterparties</th><th>Added</th><th /></tr></thead>
        <tbody>
          {d.files.map((f) => (
            <tr key={f.name}>
              <td className="mono">{f.name}</td>
              <td>{f.analysed ? f.accounts.map((a, i) => <span key={a}>{i > 0 && ", "}<Link to={`/accounts/${a}`}>{a}</Link></span>) : <span className="muted">not analysed yet</span>}</td>
              <td className="small">{f.layouts.join(", ") || "—"}</td>
              <td className="num">{num(f.n_rows)}</td>
              <td className="small">{f.time_reliable == null ? "—" : f.time_reliable ? "reliable" : <span className="muted">shuffled</span>}</td>
              <td className="small">{f.has_counterparties == null ? "—" : f.has_counterparties ? "yes" : <span className="muted">none</span>}</td>
              <td className="small">{f.original_name ? <>{f.original_name}<div className="muted">{when(f.uploaded_at)}</div></> : <span className="muted">original dataset</span>}</td>
              <td>
                <button className="link" disabled={busy || d.files.length < 2}
                  onClick={() => window.confirm(`Set ${f.name} aside and re-run the analysis without it? It can be restored later.`) && act(() => api.removeStatement(f.name))}>
                  remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {d.archives.length > 0 && (
        <>
          <h2>Set aside ({d.archives.length})</h2>
          <table>
            <thead><tr><th>When</th><th>Why</th><th>Files</th><th /></tr></thead>
            <tbody>
              {d.archives.map((a) => (
                <tr key={a.name}>
                  <td className="small">{when(a.created_at)}</td>
                  <td className="small">{a.reason === "removed" ? "removed from the dataset" : "replaced by an upload"}</td>
                  <td className="small">{a.n_files} file{a.n_files === 1 ? "" : "s"}: {a.files.slice(0, 6).join(", ")}{a.n_files > 6 ? ` and ${a.n_files - 6} more` : ""}</td>
                  <td>
                    <button className="link" disabled={busy}
                      onClick={() => window.confirm(a.reason === "removed"
                        ? "Put this statement back into the dataset and re-run the analysis?"
                        : "Swap this set back in? The current statements are set aside and the analysis re-runs.") && act(() => api.restoreArchive(a.name))}>
                      restore
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <h2>Supported statement layouts</h2>
      <p className="muted small">Each sheet is matched to one of these layouts by its columns. A statement in another layout is rejected with the columns it has; supporting it needs a new adapter in <span className="mono">backend/app/ingestion/adapters</span>.</p>
      <ul className="small">{LAYOUTS.map(([k, v]) => <li key={k}><b className="mono">{k}</b>: {v}</li>)}</ul>
      <p className="muted small">Files stay on this computer in <span className="mono">data/</span>, which git ignores. Each file becomes an account named after its number (<span className="mono">30_SOA.xlsx</span> → SOA30); uploads get the next unused number.</p>
    </>
  );
}

export function Data() {
  const dataset = useDataset();
  const [job, setJob] = useState<PipelineJob>();
  const current = job ?? dataset.data?.job;
  const running = current?.state === "running";
  const { reload } = dataset;

  // poll the background analysis; refresh everything once it ends
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => {
      api.dataJob().then((j) => {
        setJob(j);
        if (j.state !== "running") reload();
      }).catch(() => undefined);
    }, 1500);
    return () => clearInterval(t);
  }, [running, reload]);

  return (
    <div>
      <h1>Ingestion</h1>
      <p className="muted">Add new bank statements, check that Trace360 can read them, then re-run the analysis. Every screen updates when it finishes.</p>
      <Async state={dataset} what="the dataset">
        {(d) => <DataView d={current ? { ...d, job: current } : d} reload={reload} setJob={setJob} />}
      </Async>
    </div>
  );
}
