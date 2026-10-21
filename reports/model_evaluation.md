# Trace360 model evaluation (Phase 2)

Generated 2026-10-21T10:02:59. Seeds [0, 1, 2, 3, 4], contamination 0.05.

> **There are no fraud labels in this dataset, so real-world accuracy cannot be measured.** The numbers below are (a) detection of *synthetic* mule patterns injected into real weeks, (b) stability and (c) agreement checks. Read them as evidence that the models behave sensibly, not as accuracy.

## Models used and use case

| Model | What it does in Trace360 | Why this model | Limitations |
|---|---|---|---|
| Isolation Forest (scikit-learn) | Scores every account-week against all other weeks and against the account's own usual week; the most unusual 5% are flagged. Account anomaly = mean of its top-3 calibrated week scores, used as an uplift on the risk score. | Unsupervised (no labels exist), fast, robust to irrelevant features, needs no distribution assumptions. | Finds *unusual*, not *criminal*: a steady mule is not unusual for itself, and naturally extreme weeks also get flagged. Needs reliable timestamps, so SOA1-6 get no score. |
| SHAP TreeExplainer | Explains each flagged week: which features pushed it towards 'anomalous', turned into plain-English reasons. | Exact, fast attributions for tree models; makes the forest auditable by an investigator. | Explains the model, not the truth; attributions on correlated features can be split between them. |
| HDBSCAN (scikit-learn), week level | Groups active weeks (>= 10 txns) with similar behaviour and names each group by its typical pattern: collector, distributor, layering or normal-looking; outliers stay 'unclassified'. An account's role is its dominant group. | Finds the number of groups itself, handles uneven density and leaves outliers unassigned instead of forcing them. | Role names come from simple thresholds on cluster medians; with this data ~half the weeks are noise and separation is weak (see DBCV). |
| HDBSCAN, account level | Roles for the six statements without reliable timestamps, from non-temporal features (credit share, volume, round amounts, ratios). | Same reasons as above; works with 25 accounts. | Only 25 points and no timing, so it can only say collector/distributor/normal, never layering. |

## a) Synthetic injection test (closest substitute for accuracy)

For each seed the windows are split 70/30; the forest trains on the training weeks only. Copies of normal-looking test weeks get one injected mule pattern (~10% of the test set) and are scored with the untouched test weeks. Untouched weeks that happen to be genuinely unusual count as false positives, so precision is a lower bound.

| Metric (synthetic injection) | Mean ± std over 5 seeds |
|---|---|
| ROC-AUC (injected vs clean, 0.5 = chance) | 0.784 ± 0.034 |
| PR-AUC (baseline = share injected ≈ 0.10) | 0.253 ± 0.038 |
| Precision@K (K = number injected) | 0.285 ± 0.110 |
| Recall at the 5% flag threshold | 0.277 ± 0.110 |
| Precision at the threshold | 0.270 ± 0.094 |
| False-positive rate on clean test weeks | 0.081 ± 0.012 |

Recall by injected pattern (at the threshold):

| Pattern | Recall |
|---|---|
| rapid_pass_through | 0.114 ± 0.140 |
| fan_in_burst | 0.057 ± 0.070 |
| night_burst | 0.467 ± 0.194 |
| round_layering | 0.533 ± 0.221 |

Contamination trade-off:

| Contamination | Recall | Precision | FPR |
|---|---|---|---|
| 0.05 | 0.277 ± 0.110 | 0.270 ± 0.094 | 0.081 ± 0.012 |
| 0.1 | 0.469 ± 0.062 | 0.285 ± 0.041 | 0.131 ± 0.017 |

## b) Stability

| Check | Value |
|---|---|
| Jaccard overlap of flagged weeks across seeds | 0.853 ± 0.042 |
| Spearman of account anomaly ranking across seeds | 0.985 ± 0.006 |
| Time split: Spearman of later-week scores, model fit on weeks ≤ 2021-07-10 vs full model | 0.162 |
| Time split: Jaccard of flagged later weeks | 0.054 |
| Time split: share of later weeks flagged by the early model | 0.394 |
| Per-account split (first 70% of each account's weeks → last 30%): Spearman vs full model | 0.859 |
| Per-account split: Jaccard of flagged later weeks | 0.195 |
| Per-account split: share of later weeks flagged | 0.169 |

Across seeds the model is very stable. Across time it is not: a model fit on earlier weeks flags far more than 5% of later weeks, i.e. behaviour drifts and the model must be retrained when new statements arrive (training takes under a second). The global split also scores accounts whose history starts after the cutoff; the per-account split removes that effect.

## c) Agreement with the rule indicators

Spearman between account anomaly score and rule-indicator score over 19 time-reliable accounts: **0.229** (p = 0.346). The anomaly model measures change against each account's own history while the rules measure absolute mule traits, so low agreement is expected and is reported, not tuned away.

## d) HDBSCAN roles

464 active weeks clustered (321 weeks with < 10 transactions labelled 'sparse').

| Selection | Clusters | Noise share | Silhouette (non-noise) | DBCV |
|---|---|---|---|---|
| leaf | 6 | 0.444 | 0.366 | 0.191 |
| eom | 2 | 0.004 | 0.717 | 0.363 |

Chosen: 'leaf'. 'eom' scores better on DBCV but finds only two coarse groups, which cannot separate roles; 'leaf' finds interpretable groups at the cost of more noise and weaker separation.

| Cluster | Weeks | Accounts | Role | Credit share | Pass-through | Fast outflow | Dwell h | Txns/week |
|---|---|---|---|---|---|---|---|---|
| 0 | 25 | 7 | collector | 1.00 | 0.00 | 0.00 | 46.4 | 63 |
| 1 | 15 | 2 | layering | 0.84 | 0.97 | 0.58 | 1.4 | 1326 |
| 2 | 33 | 1 | layering | 0.12 | 1.00 | 0.80 | 0.5 | 122 |
| 3 | 34 | 1 | collector | 0.94 | 1.19 | 0.03 | 27.2 | 33 |
| 4 | 78 | 8 | layering | 0.18 | 0.96 | 0.49 | 1.8 | 68 |
| 5 | 73 | 8 | layering | 0.89 | 0.98 | 0.42 | 3.1 | 1938 |

Role per account:

| Account | Role | Source | Share of weeks |
|---|---|---|---|
| SOA1 | unclassified | account clusters |  |
| SOA11 | unclassified | window clusters | 12% |
| SOA12 | layering | window clusters | 44% |
| SOA14 | unclassified | window clusters | 0% |
| SOA15 | unclassified | window clusters | 6% |
| SOA16 | unclassified | window clusters | 6% |
| SOA17 | unclassified | window clusters | 10% |
| SOA18 | layering | window clusters | 50% |
| SOA19 | layering | window clusters | 28% |
| SOA2 | unclassified | account clusters |  |
| SOA20 | unclassified | window clusters | 0% |
| SOA22 | unclassified | window clusters | 21% |
| SOA23 | unclassified | window clusters | 0% |
| SOA24 | layering | window clusters | 46% |
| SOA25 | unclassified | window clusters | 8% |
| SOA26 | layering | window clusters | 42% |
| SOA28 | unclassified | window clusters | 4% |
| SOA3 | collector | account clusters |  |
| SOA4 | collector | account clusters |  |
| SOA48 | layering | window clusters | 35% |
| SOA5 | unclassified | account clusters |  |
| SOA6 | unclassified | account clusters |  |
| SOA7 | layering | window clusters | 33% |
| SOA8 | collector | window clusters | 60% |
| SOA9 | unclassified | window clusters | 0% |

## e) Top 10 accounts: Phase 1 vs Phase 2

| # | Account | Phase 1 | Phase 2 | Uplift | Flagged weeks | Role | Ring | Top reasons |
|---|---|---|---|---|---|---|---|---|
| 1 | SOA7 | 78.0 | 82.1 | +4.1 | 4 | layering | R1 | Shares 992 counterparties with other investigated accounts<br>Median time from credit to next debit is 1.2 hours<br>61% of inflow left within 2 hours |
| 2 | SOA8 | 66.7 | 76.5 | +9.9 | 13 | collector | R3 | Shares 241 counterparties with other investigated accounts<br>Week of 2020-07-27 is in the top 1% most unusual weeks (13 flagged week(s)): 2,867 round-amount transactions, unusual for this account; 85 transactions in one hour, unusual for this account; 1,736 quick credit→debit pass-throughs, unusual for this account<br>Median time from credit to next debit is 10.4 hours |
| 3 | SOA4 | 75.2 | 75.2 | +0.0 | n/a | collector | R2 | Received money from 2867 distinct counterparties<br>Typical debit (₹180,431) is 76.4x the typical credit (₹2,363)<br>Shares 772 counterparties with other investigated accounts |
| 4 | SOA9 | 70.7 | 70.7 | +0.0 | 0 | unclassified | R3 | Shares 190 counterparties with other investigated accounts<br>Median time from credit to next debit is 4.4 hours<br>Typical debit (₹713,100) is 614.7x the typical credit (₹1,160) |
| 5 | SOA2 | 69.9 | 69.9 | +0.0 | n/a | unclassified |  | Received money from 2510 distinct counterparties<br>Typical debit (₹110,544) is 44.4x the typical credit (₹2,490)<br>Shares 505 counterparties with other investigated accounts |
| 6 | SOA6 | 66.5 | 66.5 | +0.0 | n/a | unclassified | R1 | Received money from 1588 distinct counterparties<br>Sent money to 3226 distinct counterparties<br>Shares 995 counterparties with other investigated accounts |
| 7 | SOA5 | 64.4 | 64.4 | +0.0 | n/a | unclassified | R2 | Received money from 792 distinct counterparties<br>Typical debit (₹230,441) is 98.4x the typical credit (₹2,342)<br>Shares 556 counterparties with other investigated accounts |
| 8 | SOA18 | 44.5 | 58.5 | +14.0 | 5 | layering |  | Week of 2020-07-20 is in the top 1% most unusual weeks (5 flagged week(s)): 4 transactions, far above this account's usual week; 50% of the week's transactions between 00:00 and 05:00; 100% of the week's inflow left within 2 hours<br>Median time from credit to next debit is 14.7 hours<br>53% of inflow left within 2 hours |
| 9 | SOA19 | 46.6 | 57.6 | +11.0 | 2 | layering |  | 77% of inflow left within 2 hours<br>Week of 2020-05-18 is in the top 2% most unusual weeks (2 flagged week(s)): 12 night-time transactions, unusual for this account; 287 small credits (≤ ₹5,000), unusual for this account; 52 transactions in one hour, unusual for this account<br>Median time from credit to next debit is 6.8 hours |
| 10 | SOA12 | 53.5 | 54.9 | +1.4 | 0 | layering |  | 91% of inflow left within 2 hours<br>Median time from credit to next debit is 0.5 hours<br>Typical debit (₹326,912) is 346.0x the typical credit (₹945) |
