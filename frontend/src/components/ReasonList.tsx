import type { Reason } from "../api/types";
import { SourceTag } from "./Badges";

export const ReasonList = ({ reasons }: { reasons: Reason[] }) =>
  reasons.length === 0 ? (
    <p className="muted">No reason crossed the reporting threshold.</p>
  ) : (
    <ol className="reasons">
      {reasons.map((r, i) => (
        <li key={i}>
          <SourceTag source={r.source} /> {r.text} <span className="muted">(+{r.contribution.toFixed(1)} pts)</span>
        </li>
      ))}
    </ol>
  );
