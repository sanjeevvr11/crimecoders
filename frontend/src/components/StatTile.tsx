import type { ReactNode } from "react";

export const StatTile = ({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) => (
  <div className="tile">
    <div className="tile-label">{label}</div>
    <div className="tile-value">{value}</div>
    {hint && <div className="tile-hint">{hint}</div>}
  </div>
);
