export const inr = (n: number | null | undefined) =>
  n == null ? "—" : `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
export const pct = (n: number | null | undefined, digits = 0) => (n == null ? "—" : `${(n * 100).toFixed(digits)}%`);
export const num = (n: number | null | undefined, digits = 0) =>
  n == null ? "—" : n.toLocaleString("en-IN", { maximumFractionDigits: digits });
export const score = (n: number | null | undefined) => (n == null ? "—" : n.toFixed(1));
/** compact rupees for graph labels: ₹1.5 Cr, ₹3.2 L, ₹45 K */
export const inrShort = (n: number | null | undefined) => {
  if (n == null) return "—";
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(1)} Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(1)} L`;
  if (n >= 1e3) return `₹${(n / 1e3).toFixed(0)} K`;
  return `₹${n.toFixed(0)}`;
};
/** short date from an ISO timestamp, or "—" */
export const day = (iso: string | null | undefined) => (iso ? iso.slice(0, 10) : "—");
