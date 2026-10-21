"""One conclusion for the whole investigation, for the Overview screen.

Pulls together what every other screen shows (leads, money trail, network
rings, complaints, models) and turns it into plain-language findings, the
accounts to act on and a suggested next step for each. Wording stays at
"lead for investigation": there are no fraud labels in the data.
"""
import json

import pandas as pd
from fastapi import APIRouter

from app import config
from app.api.deps import get_store
from app.api.routes.accounts import account_trail_graph
from app.schemas.api import Conclusion

router = APIRouter(prefix="/api", tags=["conclusion"])

WATCH_SCORE = 45.0  # LOW accounts this close to the alert threshold go on the watchlist
WATCH_WEEKS = 3  # ... as do LOW accounts with this many unusual weeks
TOP_CHAINS = 6

VERDICT = {"HIGH": "Priority investigation", "MEDIUM": "Investigate"}
ACTION = {
    "HIGH": "Escalate: verify KYC and the account holder, review it together with {linked}, "
            "and consider a temporary debit hold while the transfers are checked.",
    "MEDIUM": "Open a case: request KYC and the purpose of the flagged transfers{linked_tail}.",
    "LOW": "Keep under watch: review the unusual weeks and re-score after new statements arrive.",
}


def inr(x: float) -> str:
    if x >= 1e7:
        return f"₹{x / 1e7:.1f} Cr"
    if x >= 1e5:
        return f"₹{x / 1e5:.1f} L"
    return f"₹{x:,.0f}"


def _list(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _sort_ids(ids) -> list[str]:
    return sorted(ids, key=lambda x: (len(x), x))


def _trail(account_id: str, has_counterparties: bool) -> dict | None:
    if not has_counterparties:
        return None
    return account_trail_graph(account_id, hops=3, direction="both", max_paths=120, shared=12)


def _account(row, reasons: dict, complaints: dict, ring_members: dict, trail: dict | None, time_reliable: bool) -> dict:
    a = row.account_id
    ring = None if pd.isna(row.ring_id) else row.ring_id
    reached = trail["summary"]["accounts_reached"] if trail else []
    linked = _sort_ids({*ring_members.get(ring, []), *reached} - {a})
    tier = row.tier if row.tier in VERDICT else "LOW"
    action = ACTION[tier].format(
        linked=_list(linked) if linked else "its counterparties",
        linked_tail=f", and check its links to {_list(linked)}" if linked else "",
    )
    t = None
    if trail and trail["summary"]["n_edges"]:
        sm = trail["summary"]
        t = {k: sm[k] for k in ("amount_in", "amount_out", "n_chains", "n_cross_account_chains", "n_circular", "n_intermediaries", "accounts_reached")}
    return {
        "account_id": a, "rank": int(row.rank), "risk_score": round(float(row.risk_score), 1), "tier": row.tier,
        "verdict": VERDICT.get(row.tier, "Monitor"),
        "role": None if pd.isna(row.role) else row.role, "ring_id": ring, "linked_accounts": linked,
        "reasons": reasons.get(a, [])[:3], "complaint_matches": int(complaints.get(a, 0)),
        "flagged_weeks": None if pd.isna(row.flagged_weeks) else int(row.flagged_weeks),
        "time_reliable": time_reliable, "trail": t, "action": action,
    }


def build_conclusion() -> dict:
    s = get_store()
    stats = s.stats()
    leads = s.table("leads").sort_values("rank")
    accounts = s.table("accounts").set_index("account_id")
    net = s.table("network_scores").set_index("account_id")
    rings = s.table("rings")
    reasons = s.table("reasons").sort_values(["account_id", "rank"]).groupby("account_id")["text"].apply(list).to_dict()
    matches = s.table("complaint_matches")
    complaints = matches.groupby("account_id")["complaint_id"].nunique().to_dict() if len(matches) else {}
    ring_members = {r.ring_id: list(r.subject_accounts) for r in rings.itertuples()}
    thr = config.ALERT_THRESHOLD
    g = s.graph
    has_cp = {a: bool(a in g and g.degree(a) > 0) for a in s.subject_ids}

    alerts = leads.loc[leads["risk_score"] >= thr]
    low = leads.loc[leads["risk_score"] < thr]
    watch = low.loc[(low["risk_score"] >= WATCH_SCORE) | (low["flagged_weeks"].fillna(0) >= WATCH_WEEKS)]

    trails = {a: _trail(a, has_cp.get(a, False)) for a in alerts["account_id"]}
    acc_out = [_account(r, reasons, complaints, ring_members, trails[r.account_id], bool(accounts.at[r.account_id, "time_reliable"]))
               for r in alerts.itertuples()]
    watch_out = [_account(r, reasons, complaints, ring_members, None, bool(accounts.at[r.account_id, "time_reliable"]))
                 for r in watch.itertuples()]

    # cross-account chains from every traced account, in money-flow order, cut to the
    # stretch between the first and last investigated account and de-duplicated
    labels, seen, chains = {}, set(), []
    for start, tg in trails.items():
        if not tg:
            continue
        labels.update({n["ref"]: n["label"] for n in tg["nodes"]})
        amount = {(e["source"], e["target"]): e["amount"] for e in tg["edges"]}
        for c in tg["chains"]:
            if c["kind"] != "cross-account":
                continue
            flow = list(reversed(c["nodes"])) if c["direction"] == "backward" else c["nodes"]
            idx = [i for i, n in enumerate(flow) if n in s.subject_ids]
            flow = flow[idx[0]: idx[-1] + 1]
            if len(flow) < 2 or tuple(flow) in seen:
                continue
            seen.add(tuple(flow))
            hop_amounts = [amount.get((u, v), 0.0) for u, v in zip(flow, flow[1:])]
            chains.append({"start": start, "nodes": flow, "amount": round(min(hop_amounts), 2), "hops": len(flow) - 1})
    chains.sort(key=lambda c: (-c["amount"], -c["hops"]))
    top_chains = [{**c, "labels": [labels.get(n, n) for n in c["nodes"]]} for c in chains[:TOP_CHAINS]]

    risk = leads.set_index("account_id")["risk_score"]
    ring_out = []
    for r in rings.sort_values("total_amount", ascending=False).itertuples():
        members = _sort_ids(r.subject_accounts)
        ring_out.append({
            "ring_id": r.ring_id, "accounts": members, "n_shared_counterparties": int(r.n_shared_counterparties),
            "total_amount": round(float(r.total_amount), 2), "max_risk": round(float(risk.reindex(members).max()), 1),
            "text": f"{_list(members)} share {r.n_shared_counterparties:,} counterparties; {inr(r.total_amount)} moved through the ring.",
        })

    n = len(leads)
    tiers = leads["tier"].value_counts().to_dict()
    n_high, n_med = int(tiers.get("HIGH", 0)), int(tiers.get("MEDIUM", 0))
    in_rings = _sort_ids({a for m in ring_members.values() for a in m})
    counts = {"accounts": n, "alerts": len(alerts), "HIGH": n_high, "MEDIUM": n_med, "LOW": int(tiers.get("LOW", 0)),
              "watchlist": len(watch), "no_action": n - len(alerts) - len(watch)}

    headline = (f"{len(alerts)} of {n} accounts show mule-account patterns and need investigation"
                f" ({n_high} high priority, {n_med} medium)." if len(alerts) else
                (f"The account does not reach the alert threshold of {thr:.0f}." if n == 1 else
                 f"None of the {n} accounts reaches the alert threshold of {thr:.0f}."))
    summary = []
    if ring_out:
        total = sum(r["total_amount"] for r in ring_out)
        summary.append(f"{len(in_rings)} of them form {len(ring_out)} ring{'s' if len(ring_out) > 1 else ''} of accounts that "
                       f"share payers and payees, with {inr(total)} moving through those rings.")
    if chains:
        summary.append(f"The money trail shows {len(chains)} distinct chains carrying money from one flagged account to another.")
    if len(watch):
        summary.append(f"{len(watch)} more account{'s are' if len(watch) > 1 else ' is'} on the watchlist and "
                       f"{counts['no_action']} need{'s' if counts['no_action'] == 1 else ''} no action now.")
    summary.append("These are leads for an investigator to confirm, not proof of fraud.")

    findings = []
    if len(alerts):
        top = alerts.iloc[0]
        role = f", {top.role} role" if isinstance(top.role, str) else ""
        findings.append({
            "tab": "Leads", "route": "/leads", "title": f"{len(alerts)} accounts flagged for investigation",
            "text": f"{len(alerts)} of {n} accounts score {thr:.0f} or more out of 100: {n_high} HIGH and {n_med} MEDIUM. "
                    f"{top.account_id} ranks first at {top.risk_score:.1f}{role}. Its strongest reason: {reasons.get(top.account_id, ['—'])[0]}.",
        })
    traced = [a for a, t in trails.items() if t and t["summary"]["n_edges"]]
    if traced:
        n_circ = len({n["ref"] for a in traced for n in trails[a]["nodes"] if n["circular"]})
        big = top_chains[0] if top_chains else None
        biggest = f" The largest: {' → '.join(big['labels'])} ({inr(big['amount'])} end to end)." if big else ""
        findings.append({
            "tab": "Money Trail", "route": f"/trail/{big['start'] if big else traced[0]}",
            "title": f"Money moves between {len({n for c in chains for n in c['nodes'] if n in s.subject_ids})} flagged accounts" if chains
                     else "Money trails traced",
            "text": f"Following the money up to 3 hops from the {len(traced)} flagged accounts that name their counterparties found "
                    f"{len(chains)} chains into another investigated account and {n_circ} points where money flows round in a circle.{biggest}",
        })
    if ring_out:
        unringed = [a for a in _sort_ids(net.index) if net.at[a, "shared_counterparties"] > 0 and a not in in_rings]
        extra = (f" {_list(unringed)} also share{'s' if len(unringed) == 1 else ''} counterparties with investigated accounts "
                 f"but {'is' if len(unringed) == 1 else 'are'} not in a ring.") if unringed else ""
        findings.append({
            "tab": "Network", "route": "/network", "title": f"{len(ring_out)} mule ring{'s' if len(ring_out) > 1 else ''} found",
            "text": " ".join(f"{r['ring_id']}: {r['text']}" for r in ring_out) + extra,
        })
    cs = stats.get("complaints", {})
    if cs.get("complaints"):
        flagged = set(alerts["account_id"])
        to_flagged = matches.loc[matches["account_id"].isin(flagged), "complaint_id"].nunique() if len(matches) else 0
        most = sorted(complaints.items(), key=lambda kv: -kv[1])[:3]
        findings.append({
            "tab": "Complaints", "route": "/complaints", "title": f"{to_flagged} complaints lead to a flagged account",
            "text": f"{cs.get('matched', 0)} of {cs['complaints']} complaints matched an account, and {cs.get('decoys_matched', 0)} of "
                    f"{cs.get('decoys', 0)} decoy complaints matched, so matching does not invent links. "
                    + (f"Most matches: {', '.join(f'{a} ({k})' for a, k in most)}. " if most else "")
                    + "The complaints are synthetic because the dataset has none.",
        })
    m = stats.get("models") or {}
    if m:
        eval_path = config.REPORTS_DIR / "model_evaluation.json"
        auc = None
        if eval_path.exists():
            auc = json.loads(eval_path.read_text()).get("injection", {}).get("roc_auc", {}).get("mean")
        roles = ", ".join(f"{k} {v}" for k, v in (m.get("roles") or {}).items())
        findings.append({
            "tab": "Models", "route": "/models", "title": f"{m.get('flagged_windows', 0)} unusual account-weeks",
            "text": f"Isolation Forest flagged {m.get('flagged_windows', 0)} of {m.get('windows', 0)} account-weeks as unusual, with SHAP "
                    f"giving the reasons for each. "
                    + (f"On planted mule patterns it scores ROC-AUC {auc:.2f}, a synthetic check rather than real-world accuracy. " if auc else "")
                    + (f"HDBSCAN behaviour roles: {roles}." if roles else ""),
        })

    n_tr = int(accounts["time_reliable"].sum())
    n_cp = sum(has_cp.values())
    limitations = [
        "There are no fraud labels, so scores are leads ranked by evidence, not confirmed verdicts.",
        f"Only {n_cp} of {n} statements name counterparties, so the money trail and rings cover those accounts only.",
        f"Only {n_tr} of {n} accounts have reliable timestamps; the others have shuffled dates, so time-based checks and the "
        "anomaly model skip them.",
        "Complaints are synthetic, generated to show the matching step.",
    ]
    next_steps = []
    high = [a["account_id"] for a in acc_out if a["tier"] == "HIGH"]
    if high:
        next_steps.append(f"Escalate {_list(high)}: verify KYC, request account-opening documents and consider temporary debit holds.")
    for r in ring_out:
        next_steps.append(f"Investigate ring {r['ring_id']} ({_list(r['accounts'])}) as one case, starting from its shared counterparties.")
    if top_chains:
        next_steps.append("Request statements for the intermediary accounts on the largest money-trail chains to follow the money further.")
    if len(watch):
        next_steps.append(f"Re-score the watchlist ({_list(_sort_ids(watch['account_id']))}) when new statements arrive.")
    next_steps.append("Download the PDF evidence report from each flagged account's page for the case file.")

    return {
        "generated_at": stats.get("generated_at", ""), "headline": headline, "summary": " ".join(summary), "counts": counts,
        "findings": findings, "accounts": acc_out, "watchlist": watch_out, "rings": ring_out, "top_chains": top_chains,
        "limitations": limitations, "next_steps": next_steps,
    }


@router.get("/conclusion", response_model=Conclusion)
def conclusion() -> dict:
    """The investigation's overall conclusion: findings per screen, accounts to act on, rings, top chains, next steps."""
    return get_store().memo("conclusion", build_conclusion)
